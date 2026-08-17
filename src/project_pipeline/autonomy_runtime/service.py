from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor


class AutonomyRuntimeService:
    """Deterministic local entry point for persistent runtime supervision."""

    def __init__(self, state_path: Path) -> None:
        self.supervisor = PersistentSupervisor(state_path)

    def health(self) -> dict[str, Any]:
        status = self.supervisor.status()
        return {
            "state": "healthy",
            "active_operation_id": status["active_operation_id"],
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
    ) -> dict[str, Any]:
        self.supervisor.compile_truth(
            control_snapshot_id=control_snapshot_id,
            sequence_id=sequence_id,
        )
        next_task = self.supervisor.select_next_work(ready_task_ids)
        if next_task is None:
            return {"state": "IDLE", "reason": "NO_READY_WORK"}
        operation_id = self.supervisor.start_operation(
            task_id=next_task,
            input_fingerprint=f"{control_snapshot_id}:{sequence_id}:{next_task}",
        )
        receipt = self.supervisor.record_result(
            operation_id=operation_id,
            worker_id=worker_id,
            output_fingerprint=f"result:{operation_id}",
            status="SUCCEEDED",
        )
        self.supervisor.complete_operation(operation_id)
        return {
            "state": "SUCCEEDED",
            "task_id": next_task,
            "operation_id": operation_id,
            "receipt": {
                "worker_id": receipt.worker_id,
                "status": receipt.status,
            },
        }
