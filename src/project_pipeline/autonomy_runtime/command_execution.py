from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PYTHON_NAMES = {"python", "python.exe", "python3", "python3.exe"}
_SHELL_METATOKENS = {";", "|", "&", "&&", "||"}
ALLOWED_MODULE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("-m", "project_pipeline", "control", "completion"),
    ("-m", "project_pipeline", "assurance", "completion-gate"),
    ("-m", "project_pipeline", "doctor"),
    ("-m", "project_pipeline", "validate"),
    ("-m", "project_pipeline", "jira", "validate"),
    ("-m", "project_pipeline", "control", "evaluate"),
    ("-m", "project_pipeline", "control", "sequence"),
    ("-m", "project_pipeline", "archive"),
    ("-m", "project_pipeline", "verify-archive"),
    ("-m", "project_pipeline", "security", "sbom"),
    ("-m", "project_pipeline", "security", "supply-chain"),
    ("-m", "project_pipeline", "security", "status"),
    ("-m", "project_pipeline", "resilience", "status"),
    ("-m", "project_pipeline", "resilience", "backup-plan"),
    ("-m", "project_pipeline", "resilience", "restore-plan"),
)
ALLOWED_SCRIPT_NAMES = frozenset(
    {
        "scripts/run_autonomy_qualification.py",
        "scripts/run_live_qualification.py",
        "scripts/run_autonomy_campaign.py",
        "scripts/campaign_probe.py",
        "scripts/autonomy_campaign_recovery_probe.py",
        "scripts/campaign_release_publication.py",
    }
)
_TAIL_CHARS = 2048
_SECRET_RE = re.compile(
    r"(?i)(authorization|api[_-]?token|api[_-]?key|secret|password|bearer)\s*[:=]\s*\S+"
)


def is_python_executable(value: str) -> bool:
    path = Path(value)
    if path.name.lower() in _PYTHON_NAMES:
        return True
    try:
        return path.resolve() == Path(sys.executable).resolve()
    except OSError:
        return False


def _normalized_script(argument: str, repository_root: Path) -> str:
    candidate = Path(argument)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(repository_root.resolve()).as_posix()
        except ValueError:
            return candidate.name
    return candidate.as_posix().replace("\\", "/")


def command_is_allowlisted(argv: list[str], *, repository_root: Path) -> bool:
    if not argv or not all(isinstance(item, str) for item in argv):
        return False
    if not is_python_executable(argv[0]):
        return False
    rest = argv[1:]
    if any(token in _SHELL_METATOKENS or "\n" in token for token in rest):
        return False
    for prefix in ALLOWED_MODULE_PREFIXES:
        if tuple(rest[: len(prefix)]) == prefix:
            return True
    if not rest:
        return False
    return _normalized_script(rest[0], repository_root) in ALLOWED_SCRIPT_NAMES


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redact_output(value: str) -> str:
    return _SECRET_RE.sub(lambda match: match.group(1) + "=REDACTED", value)


def extract_json_documents(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    documents: list[Any] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        if text[index] not in "{[":
            newline = text.find("\n", index)
            if newline < 0:
                break
            index = newline + 1
            continue
        try:
            document, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        documents.append(document)
        index = end
    return documents


def _first_mapping(documents: list[Any]) -> dict[str, Any]:
    for item in reversed(documents):
        if isinstance(item, dict):
            return item
    return {}


def command_kind(argv: list[str]) -> str:
    joined = " ".join(argv)
    if "assurance" in argv and "completion-gate" in argv:
        return "assurance.completion-gate"
    if "control" in argv and "completion" in argv:
        return "control.completion"
    if "verify-archive" in argv:
        return "release.verify-archive"
    if "archive" in argv:
        return "release.archive"
    if "security" in argv and "sbom" in argv:
        return "release.sbom"
    if "security" in argv and "supply-chain" in argv:
        return "release.supply-chain"
    if "resilience" in argv:
        return "release.resilience"
    if "jira" in argv and "validate" in argv:
        return "validate.jira"
    if "validate" in argv:
        return "validate.repository"
    if "campaign_probe.py" in joined:
        return "probe"
    if "campaign_release_publication.py" in joined:
        return "release.remote-publication"
    return "allowlisted"


def evaluate_command_semantics(
    argv: list[str],
    *,
    exit_code: int | None,
    stdout: str,
    expected_sha: str | None = None,
    expected_tree: str | None = None,
) -> dict[str, Any]:
    documents = extract_json_documents(stdout)
    payload = _first_mapping(documents)
    kind = command_kind(argv)
    if exit_code is None:
        return {
            "kind": kind,
            "result": "FAILED",
            "reason": "timeout-or-missing-exit",
            "state": None,
            "final_completion_gate_satisfied": False,
            "parsed": payload,
            "documents": documents,
        }
    if int(exit_code) != 0:
        return {
            "kind": kind,
            "result": "FAILED",
            "reason": "nonzero-exit",
            "state": payload.get("state")
            or (payload.get("completion") or {}).get("state")
            or (payload.get("completion_gate") or {}).get("state"),
            "final_completion_gate_satisfied": False,
            "parsed": payload,
            "documents": documents,
        }
    if kind == "assurance.completion-gate":
        gate = payload.get("completion_gate")
        if not isinstance(gate, dict):
            return {
                "kind": kind,
                "result": "FAILED",
                "reason": "malformed-completion-gate",
                "state": None,
                "final_completion_gate_satisfied": False,
                "parsed": payload,
                "documents": documents,
            }
        state = str(gate.get("state") or "")
        final = bool(gate.get("final_complete")) or bool(
            gate.get("final_completion_gate_satisfied")
        )
        identity_ok = True
        raw_facts = payload.get("facts")
        facts: dict[str, Any] = raw_facts if isinstance(raw_facts, dict) else {}
        if expected_sha and facts.get("integrated_sha") not in {None, expected_sha}:
            identity_ok = False
        if expected_tree and facts.get("integrated_tree") not in {None, expected_tree}:
            identity_ok = False
        ok = state == "COMPLETE" and final and identity_ok
        return {
            "kind": kind,
            "result": "PASSED" if ok else "FAILED",
            "reason": "complete"
            if ok
            else ("identity-mismatch" if not identity_ok else f"gate-{state or 'missing'}"),
            "state": state,
            "final_completion_gate_satisfied": final,
            "parsed": payload,
            "documents": documents,
        }
    if kind == "control.completion":
        completion = payload.get("completion")
        if not isinstance(completion, dict) or completion.get("schema_version") != "1.0.0":
            return {
                "kind": kind,
                "result": "FAILED",
                "reason": "malformed-control-completion",
                "state": None,
                "final_completion_gate_satisfied": False,
                "parsed": payload,
                "documents": documents,
            }
        state = str(completion.get("state") or "")
        final = bool(completion.get("final_completion_gate_satisfied"))
        return {
            "kind": kind,
            "result": "PARSED",
            "reason": "control-projection",
            "state": state,
            "final_completion_gate_satisfied": final,
            "parsed": payload,
            "documents": documents,
        }
    if kind == "probe":
        ok = payload.get("ok") is True
        return {
            "kind": kind,
            "result": "PASSED" if ok else "FAILED",
            "reason": "probe" if ok else "probe-not-ok",
            "state": None,
            "final_completion_gate_satisfied": False,
            "parsed": payload,
            "documents": documents,
        }
    if kind == "release.remote-publication":
        publication = payload.get("publication")
        if not isinstance(publication, dict):
            return {
                "kind": kind,
                "result": "FAILED",
                "reason": "malformed-remote-publication",
                "state": None,
                "final_completion_gate_satisfied": False,
                "parsed": payload,
                "documents": documents,
            }
        assets = publication.get("assets")
        identity_ok = (
            not expected_sha or publication.get("target_commitish") == expected_sha
        ) and (not expected_tree or publication.get("source_tree") == expected_tree)
        assets_ok = (
            isinstance(assets, list)
            and bool(assets)
            and all(
                isinstance(item, dict)
                and item.get("bytes_verified") is True
                and item.get("sha256") == item.get("remote_sha256")
                for item in assets
            )
        )
        published = publication.get("draft") is False and publication.get("state") == "PUBLISHED"
        ok = identity_ok and assets_ok and published
        return {
            "kind": kind,
            "result": "PASSED" if ok else "FAILED",
            "reason": "remote-publication-verified" if ok else "remote-publication-unverified",
            "state": str(publication.get("state") or ""),
            "final_completion_gate_satisfied": False,
            "parsed": payload,
            "documents": documents,
        }
    if kind.startswith("validate") or kind.startswith("release") or kind == "allowlisted":
        errors = payload.get("errors")
        valid = payload.get("valid")
        ok = True
        if isinstance(errors, list) and errors:
            ok = False
        if valid is False:
            ok = False
        if not documents and kind != "allowlisted":
            ok = False
            reason = "missing-machine-result"
        else:
            reason = "command-ok" if ok else "command-reported-failure"
        return {
            "kind": kind,
            "result": "PASSED" if ok else "FAILED",
            "reason": reason,
            "state": payload.get("state"),
            "final_completion_gate_satisfied": False,
            "parsed": payload,
            "documents": documents,
        }
    return {
        "kind": kind,
        "result": "FAILED",
        "reason": "unclassified",
        "state": None,
        "final_completion_gate_satisfied": False,
        "parsed": payload,
        "documents": documents,
    }


def execute_allowlisted_command(
    argv: list[str],
    *,
    cwd: Path,
    repository_root: Path,
    timeout_seconds: float = 120.0,
    idempotency_key: str | None = None,
    evidence_links: list[str] | None = None,
    expected_sha: str | None = None,
    expected_tree: str | None = None,
    environment_class: str = "local",
) -> dict[str, Any]:
    if not command_is_allowlisted(argv, repository_root=repository_root):
        raise ValueError("command is not on the campaign allowlist")
    encoded = json.dumps(argv, sort_keys=True)
    started = datetime.now(UTC)
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
        exit_code: int | None = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else "timeout"
    ended = datetime.now(UTC)
    stdout = redact_output(stdout)
    stderr = redact_output(stderr)
    semantics = evaluate_command_semantics(
        argv,
        exit_code=exit_code,
        stdout=stdout,
        expected_sha=expected_sha,
        expected_tree=expected_tree,
    )
    key = idempotency_key or ("CIDEMP-" + hashlib.sha256(encoded.encode()).hexdigest()[:16])
    result = semantics["result"]
    if result == "PARSED":
        result = "PASSED"
    return {
        "command": list(argv),
        "command_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "cwd": str(cwd),
        "environment_class": environment_class,
        "integrated_sha": expected_sha,
        "integrated_tree": expected_tree,
        "started_at_utc": started.isoformat(),
        "ended_at_utc": ended.isoformat(),
        "exit_code": exit_code,
        "stdout_sha256": _digest_text(stdout),
        "stderr_sha256": _digest_text(stderr),
        "stdout_tail": stdout[-_TAIL_CHARS:],
        "stderr_tail": stderr[-_TAIL_CHARS:],
        "result": result,
        "result_semantics": semantics.get("reason"),
        "semantic_state": semantics.get("state"),
        "final_completion_gate_satisfied": bool(semantics.get("final_completion_gate_satisfied")),
        "parsed_result": semantics.get("parsed") or {},
        "idempotency_key": key,
        "retry_disposition": "not-retried",
        "evidence_links": list(evidence_links or ()),
        "executed": True,
    }
