from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.persistence.migrations import SQLiteMigrationRunner

_TERMINAL_STATES = {"COMPLETED", "FAILED", "BLOCKED_EXTERNAL"}
_REQUIRED_TABLES = (
    "autonomy_runtime_meta",
    "autonomy_runtime_operations",
    "autonomy_runtime_receipts",
    "autonomy_runtime_completed_tasks",
)
_TRANSITIONS: dict[str, set[str]] = {
    "PLANNING": {"DISPATCH_INTENT_RECORDED"},
    "DISPATCH_INTENT_RECORDED": {"DISPATCHED", "UNKNOWN_OUTCOME"},
    "DISPATCHED": {"RESULT_OBSERVED", "UNKNOWN_OUTCOME"},
    "UNKNOWN_OUTCOME": {"RESULT_OBSERVED", "RECONCILED", "FAILED"},
    "RESULT_OBSERVED": {"VERIFICATION_STARTED"},
    "VERIFICATION_STARTED": {"VERIFIED_RESULT", "FAILED"},
    "VERIFIED_RESULT": {"INTEGRATION_INTENT_RECORDED"},
    "INTEGRATION_INTENT_RECORDED": {"INTEGRATED", "UNKNOWN_OUTCOME"},
    "INTEGRATED": {"RECONCILED"},
    "RECONCILED": {"COMPLETED", "BLOCKED_EXTERNAL"},
    "FAILED": {"BLOCKED_EXTERNAL"},
    "BLOCKED_EXTERNAL": set(),
    "COMPLETED": set(),
}


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
    """Restart-safe autonomous runtime supervisor with catalog-migrated SQLite state."""

    def __init__(self, state_path: Path, repository_root: Path | None = None) -> None:
        self.state_path = state_path.resolve()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        root = repository_root.resolve() if repository_root is not None else Path.cwd().resolve()
        self.repository_root = root
        self._db = sqlite3.connect(str(self.state_path))
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        SQLiteMigrationRunner(self._db, root).apply_all()
        self._assert_canonical_schema()
        self._migrate_retired_external_precondition_state()

    def _migrate_retired_external_precondition_state(self) -> None:
        retired = "HUMAN" + "_REQUIRED"
        with self._db:
            self._db.execute(
                "UPDATE autonomy_runtime_operations SET state = 'BLOCKED_EXTERNAL' WHERE state = ?",
                (retired,),
            )

    def close(self) -> None:
        self._db.close()

    def _assert_canonical_schema(self) -> None:
        present = {
            str(row["name"])
            for row in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = [name for name in _REQUIRED_TABLES if name not in present]
        if missing:
            raise RuntimeError(
                "autonomy runtime schema is missing catalog tables "
                f"{missing}; apply PPDB-0020 rather than creating tables ad hoc"
            )

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _meta_get(self, key: str, default: Any = None) -> Any:
        row = self._db.execute(
            "SELECT value_json FROM autonomy_runtime_meta WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return default
        return json.loads(str(row["value_json"]))

    def _meta_put_conn(self, key: str, value: Any) -> None:
        self._db.execute(
            """
            INSERT INTO autonomy_runtime_meta (key, value_json)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
            """,
            (key, json.dumps(value, sort_keys=True)),
        )

    def _meta_put(self, key: str, value: Any) -> None:
        with self._db:
            self._meta_put_conn(key, value)

    def _operation(self, operation_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM autonomy_runtime_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown operation: {operation_id}")
        if not isinstance(row, sqlite3.Row):
            raise TypeError("expected sqlite3.Row operation record")
        return row

    def _transition_conn(
        self, operation_id: str, next_state: str, *, when: datetime | None = None
    ) -> None:
        row = self._operation(operation_id)
        current = str(row["state"])
        allowed = _TRANSITIONS.get(current, set())
        if next_state not in allowed:
            raise ValueError(f"invalid transition {current} -> {next_state}")
        observed = _iso(when or _utc_now())
        self._db.execute(
            "UPDATE autonomy_runtime_operations SET state = ?, updated_at_utc = ? WHERE operation_id = ?",
            (next_state, observed, operation_id),
        )
        self._meta_put_conn(
            "last_transition",
            {
                "operation_id": operation_id,
                "from_state": current,
                "to_state": next_state,
                "at_utc": observed,
            },
        )

    def _transition(
        self, operation_id: str, next_state: str, *, when: datetime | None = None
    ) -> None:
        with self._db:
            self._transition_conn(operation_id, next_state, when=when)

    def compile_truth(self, *, control_snapshot_id: str, sequence_id: str) -> None:
        self._meta_put(
            "last_truth",
            {
                "control_snapshot_id": control_snapshot_id,
                "sequence_id": sequence_id,
                "compiled_at_utc": _iso(_utc_now()),
            },
        )

    def select_next_work(self, ready_task_ids: list[str]) -> str | None:
        completed = {
            str(row["task_id"])
            for row in self._db.execute(
                "SELECT task_id FROM autonomy_runtime_completed_tasks"
            ).fetchall()
        }
        failed = {
            str(row["task_id"])
            for row in self._db.execute(
                "SELECT task_id FROM autonomy_runtime_operations WHERE state IN ('FAILED', 'BLOCKED_EXTERNAL')"
            ).fetchall()
        }
        for task_id in ready_task_ids:
            if task_id not in completed and task_id not in failed:
                return task_id
        return None

    def start_operation(
        self,
        *,
        task_id: str,
        input_fingerprint: str,
        worker_id: str,
        base_branch: str,
        worktree_path: str,
        lease_fence: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> str:
        payload_json = json.dumps(payload, sort_keys=True)
        with self._db:
            existing = self._db.execute(
                "SELECT * FROM autonomy_runtime_operations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                same_input = (
                    str(existing["input_fingerprint"]) == input_fingerprint
                    and str(existing["payload_json"]) == payload_json
                    and str(existing["task_id"]) == task_id
                )
                if not same_input:
                    raise ValueError(
                        "idempotency key conflict: inputs do not match existing operation"
                    )
                return str(existing["operation_id"])
            sequence = int(self._meta_get("operation_sequence", 0)) + 1
            operation_id = f"SUP-OP-{sequence:06d}"
            now = _iso(_utc_now())
            self._db.execute(
                """
                INSERT INTO autonomy_runtime_operations (
                    operation_id, task_id, state, input_fingerprint, worker_id,
                    base_branch, worktree_path, lease_fence, attempt, idempotency_key,
                    payload_json, updated_at_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    task_id,
                    "PLANNING",
                    input_fingerprint,
                    worker_id,
                    base_branch,
                    worktree_path,
                    lease_fence,
                    1,
                    idempotency_key,
                    payload_json,
                    now,
                    now,
                ),
            )
            self._meta_put_conn("operation_sequence", sequence)
            self._meta_put_conn("active_operation_id", operation_id)
            self._transition_conn(operation_id, "DISPATCH_INTENT_RECORDED")
            return operation_id

    def mark_dispatched(self, operation_id: str) -> None:
        self._transition(operation_id, "DISPATCHED")

    def record_result(
        self,
        *,
        operation_id: str,
        worker_id: str,
        output_fingerprint: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> DispatchReceipt:
        receipt_payload = {
            "operation_id": operation_id,
            "worker_id": worker_id,
            "output_fingerprint": output_fingerprint,
            "status": status,
            "payload": payload or {},
        }
        receipt_sha = self._digest(receipt_payload)
        with self._db:
            operation_row = self._operation(operation_id)
            previous = self._db.execute(
                "SELECT receipt_sha256, payload_json, observed_at_utc FROM autonomy_runtime_receipts WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if previous is not None:
                if str(previous["receipt_sha256"]) != receipt_sha:
                    raise ValueError("duplicate operation receipt conflict")
                decoded = json.loads(str(previous["payload_json"]))
                return DispatchReceipt(
                    operation_id=operation_id,
                    task_id=str(operation_row["task_id"]),
                    worker_id=str(decoded["worker_id"]),
                    input_fingerprint=str(operation_row["input_fingerprint"]),
                    output_fingerprint=str(decoded["output_fingerprint"]),
                    status=str(decoded["status"]),
                    observed_at_utc=_from_iso(str(previous["observed_at_utc"])),
                )
            if str(operation_row["state"]) != "RESULT_OBSERVED":
                self._transition_conn(operation_id, "RESULT_OBSERVED")
            observed = _utc_now()
            self._db.execute(
                """
                UPDATE autonomy_runtime_operations
                SET worker_id = ?, result_fingerprint = ?, updated_at_utc = ?
                WHERE operation_id = ?
                """,
                (worker_id, output_fingerprint, _iso(observed), operation_id),
            )
            self._db.execute(
                """
                INSERT INTO autonomy_runtime_receipts (operation_id, receipt_sha256, payload_json, observed_at_utc)
                VALUES (?, ?, ?, ?)
                """,
                (
                    operation_id,
                    receipt_sha,
                    json.dumps(receipt_payload, sort_keys=True),
                    _iso(observed),
                ),
            )
        return DispatchReceipt(
            operation_id=operation_id,
            task_id=str(operation_row["task_id"]),
            worker_id=worker_id,
            input_fingerprint=str(operation_row["input_fingerprint"]),
            output_fingerprint=output_fingerprint,
            status=status,
            observed_at_utc=observed,
        )

    def mark_unknown_outcome(self, operation_id: str) -> None:
        self._transition(operation_id, "UNKNOWN_OUTCOME")
        with self._db:
            self._db.execute(
                "UPDATE autonomy_runtime_operations SET incident = ? WHERE operation_id = ?",
                ("UNKNOWN_OUTCOME", operation_id),
            )
            self._meta_put_conn("pending_unknown_outcome", operation_id)

    def reconcile_unknown_outcome(self, operation_id: str, *, applied: bool) -> None:
        current = self._operation(operation_id)
        if str(current["state"]) == "UNKNOWN_OUTCOME":
            if applied:
                self._transition(operation_id, "RESULT_OBSERVED")
            else:
                self._transition(operation_id, "RECONCILED")
        with self._db:
            self._db.execute(
                "UPDATE autonomy_runtime_operations SET incident = ? WHERE operation_id = ?",
                ("UNKNOWN_OUTCOME_RECONCILED", operation_id),
            )
            if self._meta_get("pending_unknown_outcome") == operation_id:
                self._meta_put_conn("pending_unknown_outcome", None)

    def mark_verified(self, operation_id: str, verification_fingerprint: str) -> None:
        with self._db:
            if str(self._operation(operation_id)["state"]) == "RESULT_OBSERVED":
                self._transition_conn(operation_id, "VERIFICATION_STARTED")
            self._db.execute(
                "UPDATE autonomy_runtime_operations SET verification_fingerprint = ? WHERE operation_id = ?",
                (verification_fingerprint, operation_id),
            )
            self._transition_conn(operation_id, "VERIFIED_RESULT")

    def mark_verification_failed(
        self, operation_id: str, verification_fingerprint: str, reason: str
    ) -> None:
        with self._db:
            if str(self._operation(operation_id)["state"]) == "RESULT_OBSERVED":
                self._transition_conn(operation_id, "VERIFICATION_STARTED")
            self._db.execute(
                """
                UPDATE autonomy_runtime_operations
                SET verification_fingerprint = ?, incident = ?
                WHERE operation_id = ?
                """,
                (verification_fingerprint, f"FAILED_VERIFICATION:{reason}", operation_id),
            )
            self._transition_conn(operation_id, "FAILED")
            if self._meta_get("active_operation_id") == operation_id:
                self._meta_put_conn("active_operation_id", None)

    def mark_integration_intent(self, operation_id: str) -> None:
        self._transition(operation_id, "INTEGRATION_INTENT_RECORDED")

    def mark_integrated(self, operation_id: str, integrated_ref: str) -> None:
        with self._db:
            if str(self._operation(operation_id)["state"]) == "VERIFIED_RESULT":
                self._transition_conn(operation_id, "INTEGRATION_INTENT_RECORDED")
            self._db.execute(
                "UPDATE autonomy_runtime_operations SET integrated_ref = ? WHERE operation_id = ?",
                (integrated_ref, operation_id),
            )
            self._transition_conn(operation_id, "INTEGRATED")
            self._transition_conn(operation_id, "RECONCILED")

    def complete_operation(self, operation_id: str) -> None:
        row = self._operation(operation_id)
        if str(row["state"]) == "UNKNOWN_OUTCOME":
            raise ValueError("cannot complete operation with unknown outcome")
        with self._db:
            if str(self._operation(operation_id)["state"]) != "COMPLETED":
                self._transition_conn(operation_id, "COMPLETED")
            self._db.execute(
                """
                INSERT INTO autonomy_runtime_completed_tasks
                    (task_id, completed_at_utc, operation_id, verified_sha)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    completed_at_utc = excluded.completed_at_utc,
                    operation_id = excluded.operation_id,
                    verified_sha = excluded.verified_sha
                """,
                (
                    str(row["task_id"]),
                    _iso(_utc_now()),
                    operation_id,
                    str(row["integrated_ref"]) if row["integrated_ref"] is not None else None,
                ),
            )
            if self._meta_get("active_operation_id") == operation_id:
                self._meta_put_conn("active_operation_id", None)

    def operation_payload(self, operation_id: str) -> dict[str, Any]:
        payload = json.loads(str(self._operation(operation_id)["payload_json"]))
        if not isinstance(payload, dict):
            raise TypeError("operation payload must be a JSON object")
        return payload

    def operation_record(self, operation_id: str) -> dict[str, Any]:
        return dict(self._operation(operation_id))

    def receipt_for(self, operation_id: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT * FROM autonomy_runtime_receipts WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def status(self) -> dict[str, Any]:
        operations = self._db.execute(
            "SELECT operation_id, task_id, state FROM autonomy_runtime_operations ORDER BY operation_id"
        ).fetchall()
        active_operation_id = self._meta_get("active_operation_id")
        if active_operation_id is not None:
            state_row = self._db.execute(
                "SELECT state FROM autonomy_runtime_operations WHERE operation_id = ?",
                (active_operation_id,),
            ).fetchone()
            if state_row is not None and str(state_row["state"]) in _TERMINAL_STATES:
                active_operation_id = None
                self._meta_put("active_operation_id", None)
        last_verified = self._db.execute(
            """
            SELECT task_id, verified_sha FROM autonomy_runtime_completed_tasks
            ORDER BY completed_at_utc DESC LIMIT 1
            """
        ).fetchone()
        return {
            "active_operation_id": active_operation_id,
            "active_operation_state": (
                None
                if active_operation_id is None
                else str(self._operation(str(active_operation_id))["state"])
            ),
            "completed_tasks": [
                str(row["task_id"])
                for row in self._db.execute(
                    "SELECT task_id FROM autonomy_runtime_completed_tasks ORDER BY task_id"
                ).fetchall()
            ],
            "operation_count": len(operations),
            "receipt_count": int(
                self._db.execute("SELECT COUNT(*) FROM autonomy_runtime_receipts").fetchone()[0]
            ),
            "last_truth": dict(self._meta_get("last_truth", {})),
            "last_transition": dict(self._meta_get("last_transition", {})),
            "pending_unknown_outcome": self._meta_get("pending_unknown_outcome"),
            "last_verified_task_id": None
            if last_verified is None
            else str(last_verified["task_id"]),
            "last_verified_sha": None
            if last_verified is None or last_verified["verified_sha"] is None
            else str(last_verified["verified_sha"]),
            "operations": [
                {
                    "operation_id": str(row["operation_id"]),
                    "task_id": str(row["task_id"]),
                    "state": str(row["state"]),
                }
                for row in operations
            ],
        }
