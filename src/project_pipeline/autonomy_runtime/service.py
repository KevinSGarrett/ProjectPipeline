from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor


class LocalSubprocessDispatchAdapter:
    def execute(self, *, command: list[str], working_directory: Path) -> dict[str, Any]:
        completed = subprocess.run(
            command,
            cwd=working_directory,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        payload["payload_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return payload


class LocalVerificationAdapter:
    def verify(self, result_payload: dict[str, Any]) -> dict[str, Any]:
        exit_code = int(result_payload.get("exit_code", 1))
        fingerprint = hashlib.sha256(
            json.dumps(result_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "verified": exit_code == 0,
            "verification_fingerprint": fingerprint,
            "reason": "exit_code_zero" if exit_code == 0 else "exit_code_non_zero",
        }


class LocalIntegrationAdapter:
    def integrate(self, *, operation_id: str, verification_fingerprint: str) -> dict[str, Any]:
        integrated_ref = hashlib.sha256(
            f"{operation_id}:{verification_fingerprint}".encode()
        ).hexdigest()
        return {"integrated_ref": integrated_ref}


class AutonomyRuntimeService:
    """Deterministic local entry point for persistent runtime supervision."""

    def __init__(
        self,
        state_path: Path,
        *,
        dispatch_adapter: LocalSubprocessDispatchAdapter | None = None,
        verification_adapter: LocalVerificationAdapter | None = None,
        integration_adapter: LocalIntegrationAdapter | None = None,
    ) -> None:
        self.supervisor = PersistentSupervisor(state_path)
        self.dispatch_adapter = dispatch_adapter or LocalSubprocessDispatchAdapter()
        self.verification_adapter = verification_adapter or LocalVerificationAdapter()
        self.integration_adapter = integration_adapter or LocalIntegrationAdapter()

    def close(self) -> None:
        self.supervisor.close()

    def health(self) -> dict[str, Any]:
        status = self.supervisor.status()
        return {
            "state": "healthy",
            "active_operation_id": status["active_operation_id"],
            "active_operation_state": status["active_operation_state"],
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
            return {
                "state": "WAITING_FOR_RECONCILIATION",
                "operation_id": active_operation_id,
                "active_operation_state": status["active_operation_state"],
            }
        next_task = self.supervisor.select_next_work(ready_task_ids)
        if next_task is None:
            return {"state": "IDLE", "reason": "NO_READY_WORK"}
        payload = task_payloads.get(next_task)
        if payload is None:
            return {
                "state": "HUMAN_REQUIRED",
                "reason": "MISSING_TASK_PAYLOAD",
                "task_id": next_task,
            }
        idempotency_key = f"{control_snapshot_id}:{sequence_id}:{next_task}"
        operation_id = self.supervisor.start_operation(
            task_id=next_task,
            input_fingerprint=idempotency_key,
            worker_id=worker_id,
            base_branch=base_branch,
            worktree_path=worktree_path,
            lease_fence=lease_fence,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        self.supervisor.mark_dispatched(operation_id)
        command = payload.get("command")
        if not isinstance(command, list) or not command:
            self.supervisor.mark_unknown_outcome(operation_id)
            return {
                "state": "UNKNOWN_OUTCOME",
                "operation_id": operation_id,
                "reason": "INVALID_COMMAND_PAYLOAD",
            }
        dispatch = self.dispatch_adapter.execute(
            command=[str(item) for item in command],
            working_directory=Path(worktree_path),
        )
        receipt = self.supervisor.record_result(
            operation_id=operation_id,
            worker_id=worker_id,
            output_fingerprint=str(dispatch["payload_sha256"]),
            status="RESULT_OBSERVED",
            payload=dispatch,
        )
        verification = self.verification_adapter.verify(dispatch)
        if not verification["verified"]:
            self.supervisor.mark_verified(operation_id, verification["verification_fingerprint"])
            self.supervisor.reconcile_unknown_outcome(operation_id, applied=False)
            return {
                "state": "FAILED_VERIFICATION",
                "task_id": next_task,
                "operation_id": operation_id,
                "verification_reason": verification["reason"],
            }
        self.supervisor.mark_verified(operation_id, verification["verification_fingerprint"])
        integration = self.integration_adapter.integrate(
            operation_id=operation_id,
            verification_fingerprint=verification["verification_fingerprint"],
        )
        self.supervisor.mark_integrated(operation_id, integration["integrated_ref"])
        self.supervisor.complete_operation(operation_id)
        return {
            "state": "SUCCEEDED",
            "task_id": next_task,
            "operation_id": operation_id,
            "receipt": {
                "worker_id": receipt.worker_id,
                "status": receipt.status,
            },
            "verification_fingerprint": verification["verification_fingerprint"],
            "integrated_ref": integration["integrated_ref"],
        }
