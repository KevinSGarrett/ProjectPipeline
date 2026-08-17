from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class DispatchReceipt:
    operation_id: str
    task_id: str
    worker_id: str
    input_fingerprint: str
    output_fingerprint: str | None
    status: str
    observed_at_utc: datetime


class PersistentSupervisor:
    """Restart-safe local supervisor for autonomous runtime lane sequencing."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {
                "schema_version": "1.0.0",
                "sequence": 0,
                "active_operation_id": None,
                "operations": {},
                "receipts": {},
                "completed_tasks": [],
                "cancelled_operations": [],
                "last_truth": {},
            }
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        payload = json.dumps(self._state, indent=2, sort_keys=True)
        self.state_path.write_text(payload + "\n", encoding="utf-8")

    def compile_truth(self, *, control_snapshot_id: str, sequence_id: str) -> None:
        self._state["last_truth"] = {
            "control_snapshot_id": control_snapshot_id,
            "sequence_id": sequence_id,
            "compiled_at_utc": _iso(_utc_now()),
        }
        self._persist()

    def select_next_work(self, ready_task_ids: list[str]) -> str | None:
        completed = set(self._state["completed_tasks"])
        for task_id in ready_task_ids:
            if task_id not in completed:
                return task_id
        return None

    def start_operation(self, *, task_id: str, input_fingerprint: str) -> str:
        self._state["sequence"] += 1
        operation_id = f"SUP-OP-{self._state['sequence']:06d}"
        self._state["operations"][operation_id] = {
            "task_id": task_id,
            "input_fingerprint": input_fingerprint,
            "state": "IN_PROGRESS",
            "started_at_utc": _iso(_utc_now()),
            "last_result_fingerprint": None,
            "unknown_outcome": False,
        }
        self._state["active_operation_id"] = operation_id
        self._persist()
        return operation_id

    def record_result(
        self,
        *,
        operation_id: str,
        worker_id: str,
        output_fingerprint: str,
        status: str,
    ) -> DispatchReceipt:
        operation = self._state["operations"][operation_id]
        previous = self._state["receipts"].get(operation_id)
        if previous is not None:
            # Idempotent replay: same output and status is accepted without mutation.
            if (
                previous["output_fingerprint"] == output_fingerprint
                and previous["status"] == status
            ):
                return DispatchReceipt(
                    operation_id=operation_id,
                    task_id=operation["task_id"],
                    worker_id=previous["worker_id"],
                    input_fingerprint=operation["input_fingerprint"],
                    output_fingerprint=output_fingerprint,
                    status=status,
                    observed_at_utc=_from_iso(previous["observed_at_utc"]),
                )
            raise ValueError("duplicate operation receipt conflict")
        observed = _utc_now()
        operation["last_result_fingerprint"] = output_fingerprint
        operation["state"] = status
        self._state["receipts"][operation_id] = {
            "worker_id": worker_id,
            "output_fingerprint": output_fingerprint,
            "status": status,
            "observed_at_utc": _iso(observed),
        }
        self._persist()
        return DispatchReceipt(
            operation_id=operation_id,
            task_id=operation["task_id"],
            worker_id=worker_id,
            input_fingerprint=operation["input_fingerprint"],
            output_fingerprint=output_fingerprint,
            status=status,
            observed_at_utc=observed,
        )

    def mark_unknown_outcome(self, operation_id: str) -> None:
        operation = self._state["operations"][operation_id]
        operation["unknown_outcome"] = True
        operation["state"] = "UNKNOWN_OUTCOME"
        self._persist()

    def reconcile_unknown_outcome(self, operation_id: str, *, applied: bool) -> None:
        operation = self._state["operations"][operation_id]
        operation["unknown_outcome"] = False
        operation["state"] = "RECONCILED_APPLIED" if applied else "RECONCILED_NOT_APPLIED"
        self._persist()

    def complete_operation(self, operation_id: str) -> None:
        operation = self._state["operations"][operation_id]
        if operation["state"] == "UNKNOWN_OUTCOME":
            raise ValueError("cannot complete operation with unknown outcome")
        operation["state"] = "COMPLETED"
        task_id = operation["task_id"]
        if task_id not in self._state["completed_tasks"]:
            self._state["completed_tasks"].append(task_id)
        if self._state.get("active_operation_id") == operation_id:
            self._state["active_operation_id"] = None
        self._persist()

    def cancel_operation(self, operation_id: str) -> None:
        operation = self._state["operations"][operation_id]
        operation["state"] = "CANCELLED"
        if operation_id not in self._state["cancelled_operations"]:
            self._state["cancelled_operations"].append(operation_id)
        if self._state.get("active_operation_id") == operation_id:
            self._state["active_operation_id"] = None
        self._persist()

    def status(self) -> dict[str, Any]:
        return {
            "active_operation_id": self._state["active_operation_id"],
            "completed_tasks": list(self._state["completed_tasks"]),
            "operation_count": len(self._state["operations"]),
            "receipt_count": len(self._state["receipts"]),
            "last_truth": dict(self._state["last_truth"]),
        }
