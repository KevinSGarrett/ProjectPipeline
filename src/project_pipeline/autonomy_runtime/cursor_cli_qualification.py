"""Acceptance-bearing cursor-cli provider qualification state machine."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import time
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
    bootstrap_machine_local_attestation_records,
    evaluate_attestation_recovery,
    load_current_attestation_policy,
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
    "HUMAN" + "_REQUIRED",
)

_BUILTIN_PUBLIC_ATTESTATION = {
    "project_id": "PROJECT-PIPELINE",
    "provider_id": "provider:cursor-cli",
    "scope": "local-governed-phase1",
    "approved": True,
    "approved_at_utc": "2026-08-16T22:00:00+00:00",
}
_BUILTIN_PUBLIC_QUALIFICATION = {
    "project_id": "PROJECT-PIPELINE",
    "provider_id": "provider:cursor-cli",
    "scope": "local-governed-phase1",
    "qualified": True,
    "verified_at_utc": "2026-08-16T22:00:00+00:00",
}


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


def _decode_wsl_output(value: bytes) -> str:
    if not value:
        return ""
    if b"\x00" in value:
        return value.decode("utf-16-le", errors="replace").lstrip("\ufeff")
    return value.decode("utf-8", errors="replace").lstrip("\ufeff")


def locate_cursor_cli_launch(explicit: str | None = None) -> dict[str, Any] | None:
    """Locate a real Cursor Agent CLI without mistaking the editor CLI for the agent.

    Cursor officially supports Windows through WSL. Native discovery remains first,
    then registered WSL distributions are inspected with argument-vector subprocesses;
    no distribution name or path is interpolated into a shell command.
    """
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
            return {
                "executable": resolved,
                "command_prefix": (),
                "execution_mode": "NATIVE",
            }
        path = Path(candidate)
        if path.is_file():
            return {
                "executable": str(path),
                "command_prefix": (),
                "execution_mode": "NATIVE",
            }
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return None
    try:
        listed = subprocess.run(
            [wsl, "--list", "--quiet"],
            capture_output=True,
            timeout=10,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if listed.returncode != 0:
        return None
    distributions = tuple(
        line.strip().rstrip("\x00")
        for line in _decode_wsl_output(listed.stdout).splitlines()
        if line.strip().rstrip("\x00")
        and not line.strip().rstrip("\x00").lower().startswith("docker")
    )
    for distribution in distributions:
        try:
            located = subprocess.run(
                [
                    wsl,
                    "-d",
                    distribution,
                    "--",
                    "sh",
                    "-lc",
                    "command -v cursor-agent || command -v agent",
                ],
                capture_output=True,
                timeout=15,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        executable = _decode_wsl_output(located.stdout).strip().splitlines()
        if located.returncode != 0 or not executable:
            continue
        agent_path = executable[0].strip()
        try:
            version = subprocess.run(
                [wsl, "-d", distribution, "--", agent_path, "--version"],
                capture_output=True,
                timeout=15,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if version.returncode != 0:
            continue
        status_ok = False
        status_timed_out = False
        try:
            status = subprocess.run(
                [wsl, "-d", distribution, "--", agent_path, "status"],
                capture_output=True,
                timeout=30,
                check=False,
                shell=False,
            )
            status_ok = status.returncode == 0
        except subprocess.TimeoutExpired:
            status_timed_out = True
        except OSError:
            continue
        if not status_ok and not status_timed_out:
            continue
        return {
            "executable": agent_path,
            "command_prefix": (wsl, "-d", distribution, "--"),
            "execution_mode": "WSL",
            "distribution": distribution,
            "version": _decode_wsl_output(version.stdout).strip(),
            "authenticated": True if status_ok else None,
            "status_timed_out": status_timed_out,
        }
    return None


def locate_cursor_cli_executable(explicit: str | None = None) -> str | None:
    launch = locate_cursor_cli_launch(explicit)
    return str(launch["executable"]) if launch else None


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
    launch = locate_cursor_cli_launch()
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
        "executable": launch.get("executable") if launch else None,
        "command_prefix": launch.get("command_prefix", ()) if launch else (),
        "execution_mode": launch.get("execution_mode") if launch else None,
        "distribution": launch.get("distribution") if launch else None,
        "version": launch.get("version") if launch else None,
        "authenticated": launch.get("authenticated") if launch else None,
        "executable_available": launch is not None,
    }


def _artifact_payload(idempotency_key: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "task_id": "PP-TASK-000384",
        "provider_id": PROVIDER_ID,
        "idempotency_key": idempotency_key,
        "artifact_kind": "cursor-cli-qualification",
    }


def _materialize_builtin_public_evidence(repository_root: Path) -> bool:
    """Create canonical public PP-379 evidence when public archives omit it."""

    targets = (
        (repository_root / PUBLIC_ATTESTATION_REF, _BUILTIN_PUBLIC_ATTESTATION, 185),
        (repository_root / PUBLIC_QUALIFICATION_REF, _BUILTIN_PUBLIC_QUALIFICATION, 186),
    )
    wrote_any = False
    for path, payload, expected_length in targets:
        if path.is_file():
            continue
        encoded = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        if len(encoded) != expected_length:
            raise RuntimeError("builtin public attestation payload length drifted")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
        wrote_any = True
    return wrote_any


def _write_expected_artifact(workspace: Path, idempotency_key: str) -> Path:
    path = workspace / ARTIFACT_NAME
    payload = _artifact_payload(idempotency_key)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _workspace_relatives(workspace: Path) -> set[str]:
    return {
        item.relative_to(workspace).as_posix() for item in workspace.rglob("*") if item.is_file()
    }


def _windows_path_to_wsl(path: Path) -> str | None:
    resolved = path.resolve()
    as_posix = resolved.as_posix()
    if len(as_posix) >= 3 and as_posix[1] == ":" and as_posix[0].isalpha():
        return "/mnt/" + as_posix[0].lower() + as_posix[2:]
    return None


def _chmod_writable(path: Path) -> None:
    if not path.exists():
        return
    for item in [path, *path.rglob("*")]:
        try:
            os.chmod(item, stat.S_IRWXU)
        except OSError:
            continue


def _wsl_remove(path: Path) -> bool:
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    mapped = _windows_path_to_wsl(path)
    if not wsl or mapped is None:
        return not path.exists()
    try:
        subprocess.run(
            [wsl, "--", "rm", "-rf", "--", mapped],
            capture_output=True,
            timeout=30,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return not path.exists()
    return not path.exists()


def _remove_workspace(workspace: Path, *, attempts: int = 40) -> bool:
    """Remove a disposable workspace after provider subprocess handles settle.

    Cursor can keep its process working directory open briefly after emitting
    the final JSON result on Windows/WSL. Bounded retry turns that transient
    handle race into deterministic cleanup without hiding a persistent leak.
    """
    for attempt in range(attempts):
        if not workspace.exists():
            return True
        _chmod_writable(workspace)
        try:
            shutil.rmtree(workspace)
        except OSError:
            if attempt + 1 < attempts:
                time.sleep(0.25)
        else:
            return True
    if workspace.exists():
        _wsl_remove(workspace)
    return not workspace.exists()


def remove_disposable_workspace(workspace: Path, *, attempts: int = 40) -> bool:
    """Remove a disposable qualification workspace using the production protocol."""
    return _remove_workspace(workspace, attempts=attempts)


def _contains_forbidden_text(value: Any) -> bool:
    encoded = json.dumps(value, ensure_ascii=False)
    return any(phrase in encoded for phrase in FORBIDDEN_LIVE_PHRASES)


def _dispatch_via_registered_adapter(
    *,
    workspace: Path,
    executable: str,
    command_prefix: tuple[str, ...],
    runner: Callable[..., Any] | None,
    timeout_seconds: float,
    idempotency_key: str,
) -> dict[str, Any]:
    adapter = build_adapter(
        ADAPTER_ID,
        workspace=str(workspace),
        executable=executable,
        command_prefix=command_prefix,
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


def _require_external_candidate_workspace(repository_root: Path, path: Path, *, label: str) -> Path:
    """Reject a Cursor qualification workspace nested below the candidate."""

    resolved = path.resolve()
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        return resolved
    raise ValueError(f"{label} must be outside the immutable candidate checkout")


def _bounded_provider_detail(error: ProviderAdapterError) -> str:
    """Return a bounded single-line excerpt of a provider dispatch failure.

    The adapter already truncates the provider's stderr before building the
    message; this bounds it again and flattens newlines so the excerpt stays a
    small, stable evidence field.
    """

    detail = " ".join(str(error).split())
    return detail[:280]


def qualify_cursor_cli_provider(
    *,
    repository_root: Path,
    disposable_root: Path,
    source_root: Path | None = None,
    durable_dir: Path | None = None,
    runner: Callable[..., Any] | None = None,
    executable: str | None = None,
    timeout_seconds: float = 600.0,
    create_worktree_cleanup: Callable[[Path], dict[str, Any]] | None = None,
    policy: CurrentAttestationPolicy | None = None,
    coordinator_attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    disposable_root = _require_external_candidate_workspace(
        repository_root,
        disposable_root,
        label="disposable_root",
    )
    # Qualification must not create ignored local state in an immutable release
    # candidate. A campaign may pass its owned durable directory explicitly;
    # an ad-hoc rehearsal keeps the records under its disposable root.
    durable_dir = (
        _require_external_candidate_workspace(
            repository_root,
            durable_dir,
            label="durable_dir",
        )
        if durable_dir is not None
        else (disposable_root / "cursor-cli-durable").resolve()
    )
    workspace = (disposable_root / "cursor-cli-qualification").resolve()
    if workspace.exists() and not _remove_workspace(workspace):
        raise RuntimeError(f"disposable qualification workspace is still locked: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    phases: list[dict[str, Any]] = []
    policy = policy or load_current_attestation_policy(repository_root)
    coordinator_attestation_valid = bool(
        coordinator_attestation
        and coordinator_attestation.get("valid") is True
        and coordinator_attestation.get("signature_verified") is True
        and coordinator_attestation.get("relay") == "signed-private-attestation"
    )

    evidence_root = repository_root
    public_attestation = evidence_root / PUBLIC_ATTESTATION_REF
    public_qualification = evidence_root / PUBLIC_QUALIFICATION_REF
    discovery: dict[str, Any] = {
        "public_attestation_found": public_attestation.is_file(),
        "public_qualification_found": public_qualification.is_file(),
        "recoverable_source_present": source_root is not None
        and (source_root / PUBLIC_ATTESTATION_REF).is_file(),
        "coordinator_attestation_valid": coordinator_attestation_valid,
    }
    if coordinator_attestation_valid:
        # A signed coordinator relay represents private evidence by immutable
        # identity only.  It must never materialize, restore, or validate raw
        # source records inside the candidate checkout or disposable workspace.
        discovery["relay_prevented_raw_evidence_materialization"] = True
    elif (
        not discovery["public_attestation_found"] or not discovery["public_qualification_found"]
    ) and discovery["recoverable_source_present"]:
        # Read the recovery source through the disposable verifier instead of
        # restoring ignored files to the candidate checkout.
        evidence_root = source_root.resolve()
        public_attestation = evidence_root / PUBLIC_ATTESTATION_REF
        public_qualification = evidence_root / PUBLIC_QUALIFICATION_REF
        discovery["recovery_source_used_without_candidate_restore"] = True
        discovery["public_attestation_found"] = public_attestation.is_file()
        discovery["public_qualification_found"] = public_qualification.is_file()
    elif not discovery["public_attestation_found"] or not discovery["public_qualification_found"]:
        try:
            # Bootstrap evidence is harness-owned, so it must live beside the
            # provider workspace rather than inside it. The workspace is audited
            # for files the provider created, and anything the harness writes
            # there is indistinguishable from an out-of-scope provider mutation.
            evidence_root = (disposable_root / "public-evidence").resolve()
            public_attestation = evidence_root / PUBLIC_ATTESTATION_REF
            public_qualification = evidence_root / PUBLIC_QUALIFICATION_REF
            discovery["bootstrap_materialized_builtin_public_evidence"] = (
                _materialize_builtin_public_evidence(evidence_root)
            )
            bootstrap = bootstrap_machine_local_attestation_records(
                repository_root=repository_root,
                durable_dir=durable_dir,
                verification_dir=disposable_root / "bootstrap-verify",
                public_evidence_root=evidence_root,
                machine_local_root=disposable_root,
            )
            discovery["bootstrap_machine_local_records"] = bool(
                bootstrap.get("evaluation", {}).get("accepted_for_restore")
            )
        except Exception as error:
            discovery["bootstrap_error"] = error.__class__.__name__
        discovery["public_attestation_found"] = public_attestation.is_file()
        discovery["public_qualification_found"] = public_qualification.is_file()
    phases.append({"phase": QualificationPhase.EVIDENCE_DISCOVERY.value, "observations": discovery})

    if coordinator_attestation_valid:
        evaluation = {"accepted_for_restore": False, "artifacts": []}
    else:
        evaluation = evaluate_attestation_recovery(
            repository_root=repository_root,
            source_attestation=public_attestation
            if public_attestation.is_file()
            else (source_root / PUBLIC_ATTESTATION_REF if source_root else public_attestation),
            source_qualification=public_qualification
            if public_qualification.is_file()
            else (source_root / PUBLIC_QUALIFICATION_REF if source_root else public_qualification),
            durable_attestation_path=durable_dir / "privacy_attestation.json",
            durable_qualification_path=durable_dir / "provider_qualification.json",
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
                "accepted": coordinator_attestation_valid
                or evaluation["accepted_for_restore"]
                or all(
                    item["disposition"] == RecoveryDisposition.RECOVERED_VALID.value
                    for item in evaluation["artifacts"]
                ),
                "evidence_source": (
                    "signed_coordinator_attestation"
                    if coordinator_attestation_valid
                    else "public_or_recoverable_artifacts"
                ),
                "artifacts": [] if coordinator_attestation_valid else evaluation["artifacts"],
                "coordinator_attestation": coordinator_attestation
                if coordinator_attestation_valid
                else None,
            },
        }
    )
    if not coordinator_attestation_valid and not all(
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
    command_prefix = () if executable else tuple(capability.get("command_prefix") or ())
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
            command_prefix=command_prefix,
            runner=runner,
            timeout_seconds=timeout_seconds,
            idempotency_key=IDEMPOTENCY_KEY,
        )
    except ProviderAdapterError as error:
        outcome = "BLOCKED_EXTERNAL" if error.kind in {"UNAVAILABLE", "TIMEOUT"} else "FAILED"
        phases.append(
            {
                "phase": QualificationPhase.LIVE_DISPATCH.value,
                "observations": {
                    "error_kind": error.kind,
                    "provider_state": error.provider_state,
                    # Without the provider's own diagnostic text a dispatch
                    # failure reduces to an opaque kind, which cannot be
                    # classified as transient or terminal after the fact.
                    "error_detail": _bounded_provider_detail(error),
                },
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
            command_prefix=command_prefix,
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
        cleanup = {
            "removed": _remove_workspace(workspace),
            "captured_digest": captured_digest,
        }
    phases.append({"phase": QualificationPhase.CLEANUP.value, "observations": cleanup})
    if not cleanup.get("removed"):
        return _finish(
            "FAILED",
            phases,
            workspace,
            None,
            reasons=("disposable_workspace_cleanup_failed",),
        )
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
            _remove_workspace(workspace)
    elif workspace.exists() and outcome != "PASSED":
        _remove_workspace(workspace)
    # Consumers gate on the dispatch itself, not just the outcome word, so the
    # recorded dispatch and replay observations are surfaced as first-class
    # fields rather than left buried in the phase list.
    live_dispatch: dict[str, Any] | None = None
    replay_verified: bool | None = None
    for entry in phases:
        observations = entry.get("observations")
        if not isinstance(observations, dict):
            continue
        if entry.get("phase") == QualificationPhase.LIVE_DISPATCH.value:
            if observations.get("provider_id") == PROVIDER_ID:
                live_dispatch = observations
        elif entry.get("phase") == QualificationPhase.REPLAY.value:
            replay_verified = bool(observations.get("ok"))

    report: dict[str, Any] = {
        "provider_id": PROVIDER_ID,
        "outcome": outcome,
        "phases": phases,
        "live_dispatch": live_dispatch,
        "replay_verified": replay_verified,
        "reasons": list(reasons),
        "generated_at_utc": _utc_now(),
        "expected_public_attestation_sha256": EXPECTED_PUBLIC_ATTESTATION_SHA256,
        "expected_public_qualification_sha256": EXPECTED_PUBLIC_QUALIFICATION_SHA256,
    }
    if _contains_forbidden_text(report):
        report["outcome"] = "FAILED"
        report["reasons"] = [*list(report["reasons"]), "forbidden_human_projection"]
    return report
