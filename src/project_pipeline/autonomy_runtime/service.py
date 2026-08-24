from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor

SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "HOMEDRIVE",
        "HOMEPATH",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
    }
)
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_OUTPUT_BYTES = 65536


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    inherited = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {item.upper() for item in SAFE_ENV_KEYS}
    }
    if extra:
        inherited.update(extra)
    return inherited


class LocalSubprocessDispatchAdapter:
    def execute(
        self,
        *,
        command: list[str],
        working_directory: Path,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not command or any(not isinstance(item, str) or not item for item in command):
            raise ValueError("command must be a non-empty argument array")
        if not working_directory.is_dir():
            raise ValueError(f"invalid worktree: {working_directory}")
        raw_stdout = ""
        raw_stderr = ""
        try:
            completed = subprocess.run(
                command,
                cwd=str(working_directory),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
                env=_safe_env(extra_env),
            )
            raw_stdout = completed.stdout
            raw_stderr = completed.stderr
            timed_out = False
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as error:
            raw_stdout = error.stdout.decode("utf-8", errors="replace") if error.stdout else ""
            raw_stderr = error.stderr.decode("utf-8", errors="replace") if error.stderr else ""
            timed_out = True
            exit_code = 124
        stdout = raw_stdout[:max_output_bytes]
        stderr = raw_stderr[:max_output_bytes]
        truncated = len(raw_stdout) > max_output_bytes or len(raw_stderr) > max_output_bytes
        payload = {
            "command": command,
            "working_directory": str(working_directory),
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "output_truncated": truncated,
            "stdout_sha256": _sha256_text(stdout),
            "stderr_sha256": _sha256_text(stderr),
        }
        payload["payload_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return payload


class LocalVerificationAdapter:
    def verify(
        self,
        result_payload: dict[str, Any],
        *,
        command: list[str],
        working_directory: Path,
        target_sha: str | None,
        verifier_id: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        if not command:
            raise ValueError("verification requires an explicit command")
        if not working_directory.is_dir():
            raise ValueError(f"invalid verification worktree: {working_directory}")
        completed = subprocess.run(
            command,
            cwd=str(working_directory),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
            env=_safe_env(),
        )
        stdout_sha = _sha256_text(completed.stdout)
        fingerprint_payload = {
            "verifier_id": verifier_id,
            "command": command,
            "working_directory": str(working_directory),
            "target_sha": target_sha,
            "exit_code": completed.returncode,
            "stdout_sha256": stdout_sha,
            "stderr_sha256": _sha256_text(completed.stderr),
            "worker_payload_sha256": result_payload.get("payload_sha256"),
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        verified = (
            completed.returncode == 0
            and bool(stdout_sha)
            and not result_payload.get("timed_out", False)
        )
        return {
            "verified": verified,
            "verification_fingerprint": fingerprint,
            "reason": "verified_command_and_output_hash"
            if verified
            else "verification_command_failed",
            "verifier_id": verifier_id,
            "command": command,
            "target_sha": target_sha,
            "exit_code": completed.returncode,
            "stdout_sha256": stdout_sha,
        }


class LocalGitIntegrationAdapter:
    def integrate(
        self,
        *,
        operation_id: str,
        source_repo: Path,
        target_repo: Path,
        source_ref: str,
        target_branch: str,
    ) -> dict[str, Any]:
        if not source_repo.is_dir() or not target_repo.is_dir():
            raise ValueError("integration requires real source and target repositories")
        source_sha = subprocess.run(
            ["git", "-C", str(source_repo), "rev-parse", "--verify", f"{source_ref}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(target_repo), "checkout", target_branch],
            check=True,
            capture_output=True,
            text=True,
        )
        if source_repo.resolve() != target_repo.resolve():
            subprocess.run(
                ["git", "-C", str(target_repo), "fetch", str(source_repo), source_ref],
                check=True,
                capture_output=True,
                text=True,
            )
            merge_ref = "FETCH_HEAD"
        else:
            merge_ref = source_sha
        subprocess.run(
            ["git", "-C", str(target_repo), "merge", "--ff-only", merge_ref],
            check=True,
            capture_output=True,
            text=True,
        )
        integrated_sha = subprocess.run(
            ["git", "-C", str(target_repo), "rev-parse", "--verify", "HEAD^{commit}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return {
            "operation_id": operation_id,
            "source_sha": source_sha,
            "integrated_ref": integrated_sha,
            "target_branch": target_branch,
        }


class AutonomyRuntimeService:
    """Deterministic local entry point for persistent runtime supervision."""

    def __init__(
        self,
        state_path: Path,
        *,
        repository_root: Path | None = None,
        dispatch_adapter: LocalSubprocessDispatchAdapter | None = None,
        verification_adapter: LocalVerificationAdapter | None = None,
        integration_adapter: LocalGitIntegrationAdapter | None = None,
    ) -> None:
        self.supervisor = PersistentSupervisor(state_path, repository_root=repository_root)
        self.dispatch_adapter = dispatch_adapter or LocalSubprocessDispatchAdapter()
        self.verification_adapter = verification_adapter or LocalVerificationAdapter()
        self.integration_adapter = integration_adapter or LocalGitIntegrationAdapter()

    def close(self) -> None:
        self.supervisor.close()

    def health(self, ready_task_ids: list[str] | None = None) -> dict[str, Any]:
        status = self.supervisor.status()
        failed = [
            item for item in status["operations"] if item["state"] in {"FAILED", "BLOCKED_EXTERNAL"}
        ]
        return {
            "state": "failed" if failed else "healthy",
            "active_operation_id": status["active_operation_id"],
            "active_operation_state": status["active_operation_state"],
            "last_transition": status["last_transition"],
            "pending_unknown_outcome": status["pending_unknown_outcome"],
            "failure_incident": failed[0] if failed else None,
            "last_verified_task_id": status["last_verified_task_id"],
            "last_verified_sha": status["last_verified_sha"],
            "next_eligible_task_id": self.supervisor.select_next_work(ready_task_ids or []),
            "operation_count": status["operation_count"],
            "receipt_count": status["receipt_count"],
        }

    def run_once(
        self,
        *,
        control_snapshot_id: str,
        sequence_id: str,
        ready_task_ids: list[str],
        worker_id: str,
        task_payloads: dict[str, dict[str, Any]],
        base_branch: str,
        worktree_path: str,
        lease_fence: str,
    ) -> dict[str, Any]:
        self.supervisor.compile_truth(
            control_snapshot_id=control_snapshot_id,
            sequence_id=sequence_id,
        )
        status = self.supervisor.status()
        active_operation_id = status["active_operation_id"]
        if active_operation_id is not None:
            return self._resume(
                active_operation_id,
                worker_id=worker_id,
                task_payloads=task_payloads,
                ready_task_ids=ready_task_ids,
            )
        next_task = self.supervisor.select_next_work(ready_task_ids)
        if next_task is None:
            return {"state": "IDLE", "reason": "NO_READY_WORK"}
        payload = task_payloads.get(next_task)
        if payload is None:
            return {
                "state": "BLOCKED_EXTERNAL",
                "reason": "MISSING_TASK_PAYLOAD",
                "task_id": next_task,
                "unavailable_capability": "task_payload",
            }
        idempotency_key = f"{control_snapshot_id}:{sequence_id}:{next_task}"
        operation_id = self.supervisor.start_operation(
            task_id=next_task,
            input_fingerprint=self.supervisor._digest(
                {"idempotency_key": idempotency_key, "payload": payload}
            ),
            worker_id=worker_id,
            base_branch=base_branch,
            worktree_path=worktree_path,
            lease_fence=lease_fence,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        return self._advance_from_intent(
            operation_id,
            worker_id=worker_id,
            payload=payload,
            ready_task_ids=ready_task_ids,
        )

    def _resume(
        self,
        operation_id: str,
        *,
        worker_id: str,
        task_payloads: dict[str, dict[str, Any]],
        ready_task_ids: list[str],
    ) -> dict[str, Any]:
        record = self.supervisor.operation_record(operation_id)
        payload = self.supervisor.operation_payload(operation_id)
        state = str(record["state"])
        if state in {"PLANNING", "DISPATCH_INTENT_RECORDED"}:
            return self._advance_from_intent(
                operation_id,
                worker_id=worker_id,
                payload=payload,
                ready_task_ids=ready_task_ids,
            )
        if state == "DISPATCHED":
            receipt = self.supervisor.receipt_for(operation_id)
            if receipt is None:
                self.supervisor.mark_unknown_outcome(operation_id)
                return {
                    "state": "UNKNOWN_OUTCOME",
                    "operation_id": operation_id,
                    "reason": "DISPATCH_RESULT_UNOBSERVED",
                    "resumed": True,
                }
            return self._verify_and_finish(
                operation_id,
                worker_id=worker_id,
                payload=payload,
                dispatch=json.loads(str(receipt["payload_json"]))["payload"],
                ready_task_ids=ready_task_ids,
            )
        if state == "UNKNOWN_OUTCOME":
            receipt = self.supervisor.receipt_for(operation_id)
            if receipt is None:
                return {
                    "state": "UNKNOWN_OUTCOME",
                    "operation_id": operation_id,
                    "reason": "WAITING_FOR_RECONCILIATION_EVIDENCE",
                    "resumed": True,
                }
            self.supervisor.reconcile_unknown_outcome(operation_id, applied=True)
            return self._verify_and_finish(
                operation_id,
                worker_id=worker_id,
                payload=payload,
                dispatch=json.loads(str(receipt["payload_json"]))["payload"],
                ready_task_ids=ready_task_ids,
            )
        if state in {"RESULT_OBSERVED", "VERIFICATION_STARTED"}:
            receipt = self.supervisor.receipt_for(operation_id)
            dispatch = (
                json.loads(str(receipt["payload_json"]))["payload"] if receipt is not None else {}
            )
            return self._verify_and_finish(
                operation_id,
                worker_id=worker_id,
                payload=payload,
                dispatch=dispatch,
                ready_task_ids=ready_task_ids,
            )
        if state in {"VERIFIED_RESULT", "INTEGRATION_INTENT_RECORDED"}:
            return self._integrate_and_finish(
                operation_id,
                payload=payload,
                ready_task_ids=ready_task_ids,
            )
        if state == "RECONCILED":
            self.supervisor.complete_operation(operation_id)
            return {
                "state": "SUCCEEDED",
                "task_id": record["task_id"],
                "operation_id": operation_id,
                "resumed": True,
                "next_eligible_task_id": self.supervisor.select_next_work(ready_task_ids),
            }
        return {
            "state": state,
            "operation_id": operation_id,
            "resumed": True,
        }

    def _advance_from_intent(
        self,
        operation_id: str,
        *,
        worker_id: str,
        payload: dict[str, Any],
        ready_task_ids: list[str],
    ) -> dict[str, Any]:
        command = payload.get("command")
        if not isinstance(command, list) or not command:
            self.supervisor.mark_unknown_outcome(operation_id)
            return {
                "state": "UNKNOWN_OUTCOME",
                "operation_id": operation_id,
                "reason": "INVALID_COMMAND_PAYLOAD",
            }
        worktree = Path(str(self.supervisor.operation_record(operation_id)["worktree_path"]))
        try:
            self.supervisor.mark_dispatched(operation_id)
            dispatch = self.dispatch_adapter.execute(
                command=[str(item) for item in command],
                working_directory=worktree,
                timeout_seconds=int(payload.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
            )
        except ValueError as error:
            self.supervisor.mark_unknown_outcome(operation_id)
            return {
                "state": "UNKNOWN_OUTCOME",
                "operation_id": operation_id,
                "reason": str(error),
            }
        if dispatch.get("timed_out"):
            receipt = self.supervisor.record_result(
                operation_id=operation_id,
                worker_id=worker_id,
                output_fingerprint=str(dispatch["payload_sha256"]),
                status="TIMEOUT",
                payload=dispatch,
            )
            self.supervisor.mark_verification_failed(
                operation_id, str(dispatch["payload_sha256"]), "timeout"
            )
            return {
                "state": "FAILED_VERIFICATION",
                "operation_id": operation_id,
                "verification_reason": "timeout",
                "receipt": {"worker_id": receipt.worker_id, "status": receipt.status},
            }
        receipt = self.supervisor.record_result(
            operation_id=operation_id,
            worker_id=worker_id,
            output_fingerprint=str(dispatch["payload_sha256"]),
            status="RESULT_OBSERVED",
            payload=dispatch,
        )
        return self._verify_and_finish(
            operation_id,
            worker_id=worker_id,
            payload=payload,
            dispatch=dispatch,
            ready_task_ids=ready_task_ids,
            receipt=receipt,
        )

    def _verify_and_finish(
        self,
        operation_id: str,
        *,
        worker_id: str,
        payload: dict[str, Any],
        dispatch: dict[str, Any],
        ready_task_ids: list[str],
        receipt: Any | None = None,
    ) -> dict[str, Any]:
        record = self.supervisor.operation_record(operation_id)
        worktree = Path(str(record["worktree_path"]))
        verify_command = payload.get("verify_command") or payload.get("command")
        if not isinstance(verify_command, list):
            self.supervisor.mark_verification_failed(operation_id, "missing", "missing_verifier")
            return {
                "state": "FAILED_VERIFICATION",
                "task_id": record["task_id"],
                "operation_id": operation_id,
                "verification_reason": "missing_verifier",
            }
        verification = self.verification_adapter.verify(
            dispatch,
            command=[str(item) for item in verify_command],
            working_directory=worktree,
            target_sha=str(payload.get("target_sha") or record.get("result_fingerprint")),
            verifier_id=str(payload.get("verifier_id") or "local-verification-adapter"),
        )
        if not verification["verified"]:
            self.supervisor.mark_verification_failed(
                operation_id,
                verification["verification_fingerprint"],
                verification["reason"],
            )
            return {
                "state": "FAILED_VERIFICATION",
                "task_id": record["task_id"],
                "operation_id": operation_id,
                "verification_reason": verification["reason"],
            }
        self.supervisor.mark_verified(operation_id, verification["verification_fingerprint"])
        return self._integrate_and_finish(
            operation_id,
            payload=payload,
            ready_task_ids=ready_task_ids,
            verification=verification,
            receipt=receipt,
        )

    def _integrate_and_finish(
        self,
        operation_id: str,
        *,
        payload: dict[str, Any],
        ready_task_ids: list[str],
        verification: dict[str, Any] | None = None,
        receipt: Any | None = None,
    ) -> dict[str, Any]:
        record = self.supervisor.operation_record(operation_id)
        source_repo = Path(str(payload.get("source_repo") or record["worktree_path"]))
        target_repo = Path(str(payload.get("target_repo") or record["worktree_path"]))
        source_ref = str(payload.get("source_ref") or "HEAD")
        target_branch = str(payload.get("target_branch") or record["base_branch"] or "main")
        if str(record["state"]) == "VERIFIED_RESULT":
            self.supervisor.mark_integration_intent(operation_id)
        try:
            integration = self.integration_adapter.integrate(
                operation_id=operation_id,
                source_repo=source_repo,
                target_repo=target_repo,
                source_ref=source_ref,
                target_branch=target_branch,
            )
        except (ValueError, subprocess.CalledProcessError) as error:
            self.supervisor.mark_unknown_outcome(operation_id)
            return {
                "state": "UNKNOWN_OUTCOME",
                "operation_id": operation_id,
                "reason": f"INTEGRATION_UNKNOWN:{error}",
            }
        self.supervisor.mark_integrated(operation_id, integration["integrated_ref"])
        self.supervisor.complete_operation(operation_id)
        return {
            "state": "SUCCEEDED",
            "task_id": record["task_id"],
            "operation_id": operation_id,
            "receipt": {
                "worker_id": getattr(receipt, "worker_id", record["worker_id"]),
                "status": getattr(receipt, "status", "RESULT_OBSERVED"),
            },
            "verification_fingerprint": None
            if verification is None
            else verification["verification_fingerprint"],
            "integrated_ref": integration["integrated_ref"],
            "next_eligible_task_id": self.supervisor.select_next_work(ready_task_ids),
        }
