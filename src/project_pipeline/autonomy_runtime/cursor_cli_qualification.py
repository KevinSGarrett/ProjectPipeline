"""Acceptance-bearing cursor-cli provider qualification state machine."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from project_pipeline.agent_router.adapters import (
    CursorCliProviderAdapter,
    ProviderAdapterError,
    build_adapter,
)
from project_pipeline.agent_router.registry import load_agent_registry
from project_pipeline.domain.agents import ExecutionTaskContract
from project_pipeline.lifecycle.attestation_recovery import (
    EXPECTED_PUBLIC_ATTESTATION_SHA256,
    EXPECTED_PUBLIC_QUALIFICATION_SHA256,
    PUBLIC_ATTESTATION_REF,
    PUBLIC_QUALIFICATION_REF,
    CurrentAttestationPolicy,
    RecoveryDisposition,
    evaluate_attestation_recovery,
    load_current_attestation_policy,
    recover_and_restore,
    sha256_bytes,
)

PROVIDER_ID = "provider:cursor-cli"
ADAPTER_ID = "adapter:cursor-cli"
IDEMPOTENCY_KEY = "pp384-cursor-cli-qualification-v1"
ARTIFACT_NAME = "pp384_cursor_cli_qualification_artifact.json"
FORBIDDEN_LIVE_PHRASES = (
    "operator session",
    "await human",
    "human-owned",
    "next human",
    "HUMAN_REQUIRED",
)


class QualificationPhase(StrEnum):
    EVIDENCE_DISCOVERY = "EVIDENCE_DISCOVERY"
    EVIDENCE_VALIDATION = "EVIDENCE_VALIDATION"
    PROVIDER_CAPABILITY = "PROVIDER_CAPABILITY"
    LIVE_DISPATCH = "LIVE_DISPATCH"
    RESULT_READBACK = "RESULT_READBACK"
    REPLAY = "REPLAY"
    CLEANUP = "CLEANUP"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def locate_cursor_cli_executable(explicit: str | None = None) -> str | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    candidates.extend(("agent", "cursor-agent"))
    search_roots = (
        Path.home() / ".local" / "bin",
        Path(r"C:\Users") / Path.home().name / ".local" / "bin",
        Path(r"C:\Program Files\cursor\tools"),
        Path.home() / "AppData" / "Roaming" / "npm",
    )
    for name in ("agent.exe", "cursor-agent.exe", "agent.cmd", "cursor-agent.cmd"):
        for root in search_roots:
            candidates.append(str(root / name))
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        path = Path(candidate)
        if path.is_file():
            return str(path)
    return None


def discover_registered_cursor_cli(repository_root: Path) -> dict[str, Any]:
    try:
        registry = load_agent_registry(repository_root)
    except Exception:
        return {"found": False, "reason": "unqualified_provider", "adapter_id": None}
    provider = next(
        (item for item in registry.providers if item.provider_id == PROVIDER_ID),
        None,
    )
    if provider is None:
        return {"found": False, "reason": "unqualified_provider", "adapter_id": None}
    if provider.adapter_id != ADAPTER_ID:
        return {
            "found": False,
            "reason": "forged_provider_identity",
            "adapter_id": provider.adapter_id,
        }
    executable = locate_cursor_cli_executable()
    return {
        "found": True,
        "provider_id": provider.provider_id,
        "adapter_id": provider.adapter_id,
        "enabled": provider.enabled,
        "qualification": next(
            (
                model.qualification.value
                for model in registry.models
                if model.provider_id == PROVIDER_ID
            ),
            "UNKNOWN",
        ),
        "executable": executable,
        "executable_available": executable is not None,
    }


def _artifact_payload(idempotency_key: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "task_id": "PP-TASK-000384",
        "provider_id": PROVIDER_ID,
        "idempotency_key": idempotency_key,
        "artifact_kind": "cursor-cli-qualification",
    }


def _write_expected_artifact(workspace: Path, idempotency_key: str) -> Path:
    path = workspace / ARTIFACT_NAME
    payload = _artifact_payload(idempotency_key)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _workspace_relatives(workspace: Path) -> set[str]:
    return {
        item.relative_to(workspace).as_posix() for item in workspace.rglob("*") if item.is_file()
    }


def _contains_forbidden_text(value: Any) -> bool:
    encoded = json.dumps(value, ensure_ascii=False)
    return any(phrase in encoded for phrase in FORBIDDEN_LIVE_PHRASES)


def _dispatch_via_registered_adapter(
    *,
    workspace: Path,
    executable: str,
    runner: Callable[..., Any] | None,
    timeout_seconds: float,
    idempotency_key: str,
) -> dict[str, Any]:
    adapter = build_adapter(
        ADAPTER_ID,
        workspace=str(workspace),
        executable=executable,
        allow_write=True,
        timeout_seconds=timeout_seconds,
        **({"runner": runner} if runner is not None else {}),
    )
    if not isinstance(adapter, CursorCliProviderAdapter):
        raise ProviderAdapterError("registered adapter was not cursor-cli", kind="FORGED_IDENTITY")
    contract = ExecutionTaskContract(
        task_id="PP-TASK-000384",
        task_class="qualification",
        required_capabilities=("code_implementation",),
        quality_tier="standard",
        risk="HIGH",
        instructions=(
            "Create exactly one disposable file named "
            f"{ARTIFACT_NAME} in the workspace root. Write the JSON object "
            f"{json.dumps(_artifact_payload(idempotency_key), sort_keys=True)} "
            "and no other files. Do not read secrets or mutate files outside the workspace."
        ),
        context={"idempotency_key": idempotency_key, "artifact": ARTIFACT_NAME},
        allow_data_egress=False,
    )
    result = adapter.execute(contract, model_name="auto")
    return {
        "provider_id": result.provider_id,
        "model_id": result.model_id,
        "finish_reason": result.finish_reason,
        "provider_request_id": result.provider_request_id,
        "usage": result.usage.model_dump(mode="json"),
        "adapter_id": adapter.adapter_id,
        "adapter_version": adapter.adapter_version,
    }


def _readback_artifact(workspace: Path, idempotency_key: str) -> dict[str, Any]:
    path = workspace / ARTIFACT_NAME
    if not path.is_file():
        return {"ok": False, "reason": "requested_artifact_missing"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    extras = _workspace_relatives(workspace) - {ARTIFACT_NAME}
    expected = _artifact_payload(idempotency_key)
    digest = sha256_bytes(path.read_bytes())
    return {
        "ok": payload == expected and not extras,
        "digest": digest,
        "extras": sorted(extras),
        "payload_matches": payload == expected,
        "path": str(path),
    }


def qualify_cursor_cli_provider(
    *,
    repository_root: Path,
    disposable_root: Path,
    source_root: Path | None = None,
    durable_dir: Path | None = None,
    runner: Callable[..., Any] | None = None,
    executable: str | None = None,
    timeout_seconds: float = 30.0,
    create_worktree_cleanup: Callable[[Path], dict[str, Any]] | None = None,
    policy: CurrentAttestationPolicy | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    workspace = (disposable_root / "cursor-cli-qualification").resolve()
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    phases: list[dict[str, Any]] = []
    policy = policy or load_current_attestation_policy(repository_root)

    public_attestation = repository_root / PUBLIC_ATTESTATION_REF
    public_qualification = repository_root / PUBLIC_QUALIFICATION_REF
    discovery = {
        "public_attestation_found": public_attestation.is_file(),
        "public_qualification_found": public_qualification.is_file(),
        "recoverable_source_present": source_root is not None
        and (source_root / PUBLIC_ATTESTATION_REF).is_file(),
    }
    if (
        not discovery["public_attestation_found"] or not discovery["public_qualification_found"]
    ) and discovery["recoverable_source_present"]:
        try:
            recover_and_restore(
                repository_root=repository_root,
                source_root=source_root,
                durable_dir=durable_dir,
                verification_dir=disposable_root / "recovery-verify",
                apply=True,
            )
        except Exception as error:
            discovery["recovery_error"] = error.__class__.__name__
        discovery["public_attestation_found"] = public_attestation.is_file()
        discovery["public_qualification_found"] = public_qualification.is_file()
    phases.append({"phase": QualificationPhase.EVIDENCE_DISCOVERY.value, "observations": discovery})

    evaluation = evaluate_attestation_recovery(
        repository_root=repository_root,
        source_attestation=public_attestation
        if public_attestation.is_file()
        else (source_root / PUBLIC_ATTESTATION_REF if source_root else public_attestation),
        source_qualification=public_qualification
        if public_qualification.is_file()
        else (source_root / PUBLIC_QUALIFICATION_REF if source_root else public_qualification),
        durable_attestation_path=(
            (durable_dir or repository_root / ".local" / "state" / "takeover")
            / "privacy_attestation.json"
        ),
        durable_qualification_path=(
            (durable_dir or repository_root / ".local" / "state" / "takeover")
            / "provider_qualification.json"
        ),
        verification_dir=disposable_root / "evidence-verify",
        historical_receipt_path=repository_root
        / "evidence"
        / "control_completion_post_remediation.json",
        policy=policy,
    )
    phases.append(
        {
            "phase": QualificationPhase.EVIDENCE_VALIDATION.value,
            "observations": {
                "accepted": evaluation["accepted_for_restore"]
                or all(
                    item["disposition"] == RecoveryDisposition.RECOVERED_VALID.value
                    for item in evaluation["artifacts"]
                ),
                "artifacts": evaluation["artifacts"],
            },
        }
    )
    if not all(
        item["disposition"] == RecoveryDisposition.RECOVERED_VALID.value
        for item in evaluation["artifacts"]
    ):
        missing = not any(
            item["disposition"] != RecoveryDisposition.MISSING.value
            for item in evaluation["artifacts"]
        )
        stale = any(
            item["disposition"] == RecoveryDisposition.RECOVERED_BUT_STALE.value
            for item in evaluation["artifacts"]
        )
        if missing and not discovery["recoverable_source_present"]:
            return _finish(
                "FAILED",
                phases,
                workspace,
                create_worktree_cleanup,
                reasons=("missing evidence with no recoverable source",),
            )
        invalid_ts = any(
            reason
            in {
                "missing_or_invalid_timestamp",
                "missing_or_invalid_provider_qualification_timestamp",
            }
            for item in evaluation["artifacts"]
            for reason in item.get("validator_reasons", [])
        )
        if invalid_ts:
            return _finish(
                "FAILED",
                phases,
                workspace,
                create_worktree_cleanup,
                reasons=("invalid timestamp",),
            )
        if stale:
            return _finish(
                "FAILED",
                phases,
                workspace,
                create_worktree_cleanup,
                reasons=("stale timestamp under a finite policy",),
            )
        return _finish(
            "FAILED",
            phases,
            workspace,
            create_worktree_cleanup,
            reasons=("evidence validation failed",),
        )

    capability = discover_registered_cursor_cli(repository_root)
    resolved_executable = executable or capability.get("executable")
    capability["resolved_executable"] = resolved_executable
    phases.append(
        {"phase": QualificationPhase.PROVIDER_CAPABILITY.value, "observations": capability}
    )
    if not capability.get("found"):
        return _finish(
            "FAILED",
            phases,
            workspace,
            create_worktree_cleanup,
            reasons=(capability.get("reason") or "unqualified_provider",),
        )
    if runner is None and not resolved_executable:
        return _finish(
            "BLOCKED_EXTERNAL",
            phases,
            workspace,
            create_worktree_cleanup,
            reasons=("cursor-cli executable unavailable after autonomous discovery",),
        )

    dispatch_observations: dict[str, Any]
    try:
        dispatch_observations = _dispatch_via_registered_adapter(
            workspace=workspace,
            executable=str(resolved_executable or "agent"),
            runner=runner,
            timeout_seconds=timeout_seconds,
            idempotency_key=IDEMPOTENCY_KEY,
        )
    except ProviderAdapterError as error:
        outcome = "BLOCKED_EXTERNAL" if error.kind in {"UNAVAILABLE", "TIMEOUT"} else "FAILED"
        phases.append(
            {
                "phase": QualificationPhase.LIVE_DISPATCH.value,
                "observations": {"error_kind": error.kind, "provider_state": error.provider_state},
            }
        )
        return _finish(
            outcome,
            phases,
            workspace,
            create_worktree_cleanup,
            reasons=(error.kind.lower(),),
        )
    if dispatch_observations.get("provider_id") != PROVIDER_ID:
        return _finish(
            "FAILED",
            phases,
            workspace,
            create_worktree_cleanup,
            reasons=("forged_provider_identity",),
        )
    phases.append(
        {"phase": QualificationPhase.LIVE_DISPATCH.value, "observations": dispatch_observations}
    )

    first_readback = _readback_artifact(workspace, IDEMPOTENCY_KEY)
    phases.append(
        {"phase": QualificationPhase.RESULT_READBACK.value, "observations": first_readback}
    )
    if not first_readback["ok"]:
        reason = (
            "out-of-scope mutation"
            if first_readback.get("extras")
            else first_readback.get("reason") or "readback_failed"
        )
        return _finish(
            "FAILED",
            phases,
            workspace,
            create_worktree_cleanup,
            reasons=(str(reason),),
        )

    replay_observations: dict[str, Any]
    try:
        replay_observations = _dispatch_via_registered_adapter(
            workspace=workspace,
            executable=str(resolved_executable or "agent"),
            runner=runner,
            timeout_seconds=timeout_seconds,
            idempotency_key=IDEMPOTENCY_KEY,
        )
    except ProviderAdapterError as error:
        return _finish(
            "FAILED",
            phases,
            workspace,
            create_worktree_cleanup,
            reasons=(f"replay_{error.kind.lower()}",),
        )
    second_readback = _readback_artifact(workspace, IDEMPOTENCY_KEY)
    replay_ok = (
        second_readback["ok"]
        and second_readback["digest"] == first_readback["digest"]
        and replay_observations.get("provider_id") == PROVIDER_ID
    )
    phases.append(
        {
            "phase": QualificationPhase.REPLAY.value,
            "observations": {
                "ok": replay_ok,
                "first_digest": first_readback["digest"],
                "second_digest": second_readback.get("digest"),
            },
        }
    )
    if not replay_ok:
        return _finish(
            "FAILED",
            phases,
            workspace,
            create_worktree_cleanup,
            reasons=("conflicting replay",),
        )

    cleanup = {"removed": False}
    if create_worktree_cleanup is not None:
        cleanup = create_worktree_cleanup(workspace)
    elif workspace.exists():
        captured_digest = first_readback["digest"]
        shutil.rmtree(workspace)
        cleanup = {"removed": not workspace.exists(), "captured_digest": captured_digest}
    phases.append({"phase": QualificationPhase.CLEANUP.value, "observations": cleanup})
    return _finish("PASSED", phases, workspace, None, reasons=())


def _finish(
    outcome: str,
    phases: list[dict[str, Any]],
    workspace: Path,
    cleanup: Callable[[Path], dict[str, Any]] | None,
    *,
    reasons: tuple[str, ...],
) -> dict[str, Any]:
    if cleanup is not None and workspace.exists():
        try:
            cleanup(workspace)
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
    elif workspace.exists() and outcome != "PASSED":
        shutil.rmtree(workspace, ignore_errors=True)
    report = {
        "provider_id": PROVIDER_ID,
        "outcome": outcome,
        "phases": phases,
        "reasons": list(reasons),
        "generated_at_utc": _utc_now(),
        "expected_public_attestation_sha256": EXPECTED_PUBLIC_ATTESTATION_SHA256,
        "expected_public_qualification_sha256": EXPECTED_PUBLIC_QUALIFICATION_SHA256,
    }
    if _contains_forbidden_text(report):
        report["outcome"] = "FAILED"
        report["reasons"] = [*list(report["reasons"]), "forbidden_human_projection"]
    return report
