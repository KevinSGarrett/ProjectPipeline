"""Context pack compile, transfer, worker consumption, and native test execution."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from project_pipeline.autonomy_runtime.worker_runtime_identity import local_runtime_identity
from project_pipeline.context_engine.service import ContextService
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPolicy,
    ContextSourceKind,
    ContextTrust,
    DelegationEnvelope,
    ReceiptStatus,
    Sensitivity,
)

CANARY = "SYNTHETIC_SECRET_CANARY_NOT_A_CREDENTIAL"
NATIVE_PASS = "tests/fixtures/cycle21_native_pass.py"
NATIVE_FAIL = "tests/fixtures/cycle21_native_fail.py"


def job_input_digest(
    *,
    task_id: str,
    source_sha: str,
    source_tree: str,
    overlay_sha256: str,
    pack_sha256: str,
    selection: tuple[str, ...],
) -> str:
    body = {
        "task_id": task_id,
        "source_sha": source_sha,
        "source_tree": source_tree,
        "overlay_sha256": overlay_sha256,
        "pack_sha256": pack_sha256,
        "selection": list(selection),
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compile_validation_pack(
    *,
    root: Path,
    database: Path,
    task_id: str,
    source_sha: str,
    source_tree: str,
    overlay_sha256: str,
    selection: tuple[str, ...],
    host_id: str,
    principal: str,
) -> dict[str, Any]:
    objective = f"Execute native validation for {task_id}"
    envelope = DelegationEnvelope.create(
        objective=objective,
        return_protocol="return junit and artifact manifest",
        required_context_keys=("source_binding", "test_selection", "authority"),
        expected_outputs=("junit.xml", "artifact_manifest.json"),
        acceptance_criteria=("tests_collected", "nonzero_exit_is_failure"),
        authority_scope=(host_id, principal),
        source_references=(source_sha, source_tree, overlay_sha256),
    )
    generated = datetime.now(UTC)
    candidates = (
        ContextCandidate(
            context_key="source_binding",
            kind=ContextSourceKind.REQUIREMENT,
            content=json.dumps(
                {
                    "source_sha": source_sha,
                    "source_tree": source_tree,
                    "overlay_sha256": overlay_sha256,
                    "task_id": task_id,
                },
                sort_keys=True,
            ),
            revision_id=source_sha,
            observed_at_utc=generated,
            trust=ContextTrust.SOURCE_CONTROLLED,
            sensitivity=Sensitivity.INTERNAL,
        ),
        ContextCandidate(
            context_key="test_selection",
            kind=ContextSourceKind.TEST,
            content=json.dumps({"selection": list(selection)}, sort_keys=True),
            revision_id="cycle21-native",
            observed_at_utc=generated,
            trust=ContextTrust.SOURCE_CONTROLLED,
            sensitivity=Sensitivity.INTERNAL,
        ),
        ContextCandidate(
            context_key="authority",
            kind=ContextSourceKind.POLICY,
            content=json.dumps(
                {"host_id": host_id, "principal": principal, "canary": CANARY},
                sort_keys=True,
            ),
            revision_id=principal,
            observed_at_utc=generated,
            trust=ContextTrust.SOURCE_CONTROLLED,
            sensitivity=Sensitivity.INTERNAL,
        ),
    )
    policy = ContextPolicy(policy_version="CTX-POLICY-21.0")
    with ContextService(root=root, database=database) as service:
        pack = service.compile(envelope, candidates, policy)
        payload = json.dumps(pack.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        return {
            "ok": True,
            "pack": pack.model_dump(mode="json"),
            "pack_id": pack.pack_id,
            "pack_sha256": pack.content_sha256,
            "artifact_sha256": digest,
            "delegation_id": envelope.delegation_id,
            "canary_present": CANARY in json.dumps(pack.model_dump(mode="json")),
        }


def write_pack(workspace: Path, pack: dict[str, Any]) -> Path:
    path = workspace / "context_pack.json"
    path.write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def consume_pack_on_worker(payload: dict[str, Any]) -> dict[str, Any]:
    live = local_runtime_identity()
    pack_path = Path(str(payload.get("pack_path") or payload.get("workspace") or "")).resolve()
    if pack_path.is_dir():
        pack_path = pack_path / "context_pack.json"
    if not pack_path.is_file():
        return {"ok": False, "reason": "pack_missing", "exit_code": 2}
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"ok": False, "reason": "pack_unreadable", "exit_code": 2}
    expected = str(payload.get("pack_sha256") or "")
    actual = hashlib.sha256(
        json.dumps(pack, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if expected and actual != expected and str(pack.get("content_sha256") or "") != expected:
        return {"ok": False, "reason": "pack_tampered", "exit_code": 2}
    binding = _pack_item(pack, "source_binding")
    if str(binding.get("source_sha") or "") != str(payload.get("source_sha") or ""):
        return {"ok": False, "reason": "wrong_source", "exit_code": 2}
    if str(binding.get("source_tree") or "") != str(payload.get("source_tree") or ""):
        return {"ok": False, "reason": "wrong_tree", "exit_code": 2}
    authority = _pack_item(pack, "authority")
    if str(authority.get("host_id") or "") != str(payload.get("host_id") or ""):
        return {"ok": False, "reason": "wrong_host", "exit_code": 2}
    if str(authority.get("principal") or "") != str(payload.get("principal") or ""):
        return {"ok": False, "reason": "wrong_principal", "exit_code": 2}
    if str(payload.get("project_id") or "PROJECT-PIPELINE") not in {
        "PROJECT-PIPELINE",
        str(binding.get("task_id") or payload.get("job_id") or ""),
    } and str(payload.get("project_id") or "") not in {"", "PROJECT-PIPELINE"}:
        return {"ok": False, "reason": "wrong_project", "exit_code": 2}
    generated = pack.get("generated_at_utc")
    try:
        generated_at = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
        if (datetime.now(UTC) - generated_at.astimezone(UTC)).total_seconds() > 86_400:
            return {"ok": False, "reason": "pack_stale", "exit_code": 2}
    except ValueError:
        return {"ok": False, "reason": "pack_stale", "exit_code": 2}
    worker_id = f"{live.get('hostname')}:{os.getpid()}"
    receipt = {
        "ok": True,
        "pack_id": pack.get("pack_id"),
        "worker_id": worker_id,
        "consumed_at_utc": datetime.now(UTC).isoformat(),
        "status": ReceiptStatus.CONSUMED.value,
        "host_id": payload.get("host_id"),
        "principal": payload.get("principal"),
        "pack_sha256": pack.get("content_sha256"),
        "live_hostname": live.get("hostname"),
    }
    receipt_path = pack_path.with_name("context_receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def execute_native_tests(
    *,
    root: Path,
    selection: tuple[str, ...],
    output_dir: Path,
    python_executable: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    junit = output_dir / "junit.xml"
    interpreter = python_executable or sys.executable
    argv = [
        interpreter,
        "-m",
        "pytest",
        "-q",
        f"--junitxml={junit}",
        *selection,
    ]
    completed = subprocess.run(
        argv,
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    collected, failed, skipped = _junit_counts(junit)
    logs = (completed.stdout or "")[:65536]
    stderr = (completed.stderr or "")[:65536]
    if completed.returncode != 0:
        status = "FAIL"
    elif collected == 0:
        status = "NO_TESTS"
    elif skipped and collected == skipped:
        status = "MANDATORY_SKIPPED"
    else:
        status = "PASS"
    artifacts = {
        "junit.xml": _file_digest(junit) if junit.is_file() else None,
    }
    manifest = {
        "ok": status == "PASS",
        "status": status,
        "selection": list(selection),
        "command": argv,
        "exit_code": completed.returncode,
        "collected": collected,
        "failed": failed,
        "skipped": skipped,
        "tests_run": collected,
        "stdout": logs,
        "stderr": stderr,
        "junit_path": str(junit) if junit.is_file() else None,
        "junit_sha256": artifacts["junit.xml"],
        "artifact_sha256": artifacts["junit.xml"] or hashlib.sha256(b"").hexdigest(),
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def verify_output_contract(
    manifest: dict[str, Any], *, artifact_bytes: bytes | None
) -> dict[str, Any]:
    if not manifest.get("ok"):
        return {"ok": False, "reason": "tests_not_passed"}
    if int(manifest.get("collected") or 0) < 1:
        return {"ok": False, "reason": "no_tests_collected"}
    if int(manifest.get("skipped") or 0) and int(manifest.get("collected")) == int(
        manifest.get("skipped") or 0
    ):
        return {"ok": False, "reason": "mandatory_skipped"}
    if int(manifest.get("exit_code") or 0) != 0:
        return {"ok": False, "reason": "nonzero_exit"}
    digest = str(manifest.get("junit_sha256") or "")
    if artifact_bytes is not None:
        actual = hashlib.sha256(artifact_bytes).hexdigest()
        if actual != digest:
            return {"ok": False, "reason": "artifact_digest_mismatch"}
    envelope_digest = str(manifest.get("envelope_sha256") or "")
    if envelope_digest and envelope_digest == digest:
        return {"ok": False, "reason": "envelope_digest_is_not_artifact"}
    return {"ok": True}


def _pack_item(pack: dict[str, Any], key: str) -> dict[str, Any]:
    for item in pack.get("items") or []:
        if isinstance(item, dict) and item.get("context_key") == key:
            try:
                loaded = json.loads(str(item.get("content") or "{}"))
            except json.JSONDecodeError:
                return {}
            return loaded if isinstance(loaded, dict) else {}
    return {}


def _junit_counts(path: Path) -> tuple[int, int, int]:
    if not path.is_file():
        return (0, 0, 0)
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError:
        return (0, 0, 0)
    suites = [root] if root.tag.endswith("testsuite") else list(root)
    collected = 0
    failed = 0
    skipped = 0
    for suite in suites:
        collected += int(suite.attrib.get("tests") or 0)
        failed += int(suite.attrib.get("failures") or 0) + int(suite.attrib.get("errors") or 0)
        skipped += int(suite.attrib.get("skipped") or 0)
    return (collected, failed, skipped)


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_selection(*, failing: bool = False) -> tuple[str, ...]:
    return (NATIVE_FAIL,) if failing else (NATIVE_PASS,)
