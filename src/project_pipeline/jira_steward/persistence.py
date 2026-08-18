from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.domain.jira import (
    JiraOperationState,
    JiraReconciliationPlan,
    JiraRemoteSnapshot,
    JiraSyncReceipt,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class JiraSyncPersistenceError(RuntimeError):
    """Raised when synchronization state cannot be persisted transactionally."""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JiraSyncStore:
    """Transactional local outbox, snapshot, mapping, plan, and receipt store."""

    def __init__(
        self,
        connection_or_path: sqlite3.Connection | Path | str,
        repository_root: Path,
        *,
        owns_connection: bool | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        if isinstance(connection_or_path, sqlite3.Connection):
            self.connection = connection_or_path
            self._owns_connection = False if owns_connection is None else owns_connection
        else:
            path = connection_or_path
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(path), isolation_level=None, timeout=30.0)
            self._owns_connection = True if owns_connection is None else owns_connection
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 30000")

    def __enter__(self) -> JiraSyncStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self.connection.in_transaction:
            yield self.connection
            return
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def initialize(self) -> dict[str, Any]:
        status = SQLiteMigrationRunner(self.connection, self.repository_root).apply_all()
        return status.as_dict()

    def put_snapshot(self, snapshot: JiraRemoteSnapshot) -> None:
        self.initialize()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO jira_remote_snapshots (
                    snapshot_id, project_key, source, fingerprint, complete,
                    snapshot_json, observed_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    observed_at_utc = excluded.observed_at_utc
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.project_key,
                    snapshot.source.value,
                    snapshot.fingerprint,
                    int(snapshot.complete),
                    _json(snapshot.model_dump(mode="json")),
                    snapshot.observed_at_utc.isoformat(),
                ),
            )

    def get_snapshot(self, snapshot_id: str) -> JiraRemoteSnapshot | None:
        self.initialize()
        row = self.connection.execute(
            "SELECT snapshot_json FROM jira_remote_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return None if row is None else JiraRemoteSnapshot.model_validate_json(row[0])

    def put_plan(self, plan: JiraReconciliationPlan) -> None:
        self.initialize()
        with self.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM jira_remote_snapshots WHERE snapshot_id = ?",
                    (plan.remote_snapshot_id,),
                ).fetchone()
                is None
            ):
                raise JiraSyncPersistenceError(
                    f"remote snapshot is not persisted: {plan.remote_snapshot_id}"
                )
            connection.execute(
                """
                INSERT INTO jira_reconciliation_plans (
                    plan_id, project_key, authority_mode, local_fingerprint,
                    remote_snapshot_id, remote_fingerprint, plan_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET plan_json = excluded.plan_json
                """,
                (
                    plan.plan_id,
                    plan.project_key,
                    plan.authority_mode.value,
                    plan.local_fingerprint,
                    plan.remote_snapshot_id,
                    plan.remote_fingerprint,
                    _json(plan.model_dump(mode="json")),
                    plan.created_at_utc.isoformat(),
                ),
            )
            for operation in plan.operations:
                timestamp = plan.created_at_utc.isoformat()
                connection.execute(
                    """
                    INSERT INTO jira_sync_operations (
                        operation_id, plan_id, operation_type, local_id, remote_key,
                        idempotency_key, request_fingerprint, operation_state,
                        requires_remote_write, requires_human_approval, operation_json,
                        error_json, external_operation_id, created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                    ON CONFLICT(operation_id) DO UPDATE SET
                        operation_json = excluded.operation_json,
                        updated_at_utc = excluded.updated_at_utc
                    """,
                    (
                        operation.operation_id,
                        plan.plan_id,
                        operation.operation_type.value,
                        operation.local_id,
                        operation.remote_key,
                        operation.idempotency_key,
                        operation.request_fingerprint,
                        operation.state.value,
                        int(operation.requires_remote_write),
                        int(operation.requires_independent_verification),
                        _json(operation.model_dump(mode="json")),
                        timestamp,
                        timestamp,
                    ),
                )

    def get_plan(self, plan_id: str) -> JiraReconciliationPlan | None:
        self.initialize()
        row = self.connection.execute(
            "SELECT plan_json FROM jira_reconciliation_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        return None if row is None else JiraReconciliationPlan.model_validate_json(row[0])

    def operation_state(self, operation_id: str) -> JiraOperationState | None:
        self.initialize()
        row = self.connection.execute(
            "SELECT operation_state FROM jira_sync_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return None if row is None else JiraOperationState(str(row[0]))

    def set_operation_state(
        self,
        operation_id: str,
        state: JiraOperationState,
        *,
        error: Mapping[str, Any] | None = None,
        external_operation_id: str | None = None,
    ) -> None:
        self.initialize()
        with self.transaction() as connection:
            updated = connection.execute(
                """
                UPDATE jira_sync_operations
                SET operation_state = ?, error_json = ?, external_operation_id = ?, updated_at_utc = ?
                WHERE operation_id = ?
                """,
                (
                    state.value,
                    None if error is None else _json(dict(error)),
                    external_operation_id,
                    _now(),
                    operation_id,
                ),
            )
            if updated.rowcount != 1:
                raise JiraSyncPersistenceError(f"Jira operation not found: {operation_id}")

    def put_remote_mapping(
        self,
        *,
        local_id: str,
        remote_key: str,
        provider_id: str,
        source_operation_id: str | None,
        remote_fingerprint: str | None,
    ) -> None:
        self.initialize()
        timestamp = _now()
        with self.transaction() as connection:
            existing_by_local = connection.execute(
                "SELECT remote_key FROM jira_remote_mappings WHERE local_id = ?", (local_id,)
            ).fetchone()
            existing_by_remote = connection.execute(
                "SELECT local_id FROM jira_remote_mappings WHERE remote_key = ?", (remote_key,)
            ).fetchone()
            if existing_by_local is not None and str(existing_by_local[0]) != remote_key:
                raise JiraSyncPersistenceError(
                    f"local Jira ID {local_id} is already mapped to {existing_by_local[0]}"
                )
            if existing_by_remote is not None and str(existing_by_remote[0]) != local_id:
                raise JiraSyncPersistenceError(
                    f"remote Jira key {remote_key} is already mapped to {existing_by_remote[0]}"
                )
            connection.execute(
                """
                INSERT INTO jira_remote_mappings (
                    local_id, remote_key, provider_id, first_observed_at_utc,
                    last_observed_at_utc, source_operation_id, remote_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(local_id) DO UPDATE SET
                    remote_key = excluded.remote_key,
                    provider_id = excluded.provider_id,
                    last_observed_at_utc = excluded.last_observed_at_utc,
                    source_operation_id = COALESCE(excluded.source_operation_id, jira_remote_mappings.source_operation_id),
                    remote_fingerprint = excluded.remote_fingerprint
                """,
                (
                    local_id,
                    remote_key,
                    provider_id,
                    timestamp,
                    timestamp,
                    source_operation_id,
                    remote_fingerprint,
                ),
            )

    def remote_key_for(self, local_id: str) -> str | None:
        self.initialize()
        row = self.connection.execute(
            "SELECT remote_key FROM jira_remote_mappings WHERE local_id = ?", (local_id,)
        ).fetchone()
        return None if row is None else str(row[0])

    def local_id_for(self, remote_key: str) -> str | None:
        self.initialize()
        row = self.connection.execute(
            "SELECT local_id FROM jira_remote_mappings WHERE remote_key = ?", (remote_key,)
        ).fetchone()
        return None if row is None else str(row[0])

    def put_receipt(self, receipt: JiraSyncReceipt) -> None:
        self.initialize()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO jira_sync_receipts (
                    receipt_id, plan_id, mode, result, receipt_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(receipt_id) DO UPDATE SET receipt_json = excluded.receipt_json
                """,
                (
                    receipt.receipt_id,
                    receipt.plan_id,
                    receipt.mode.value,
                    receipt.result,
                    _json(receipt.model_dump(mode="json")),
                    receipt.created_at_utc.isoformat(),
                ),
            )

    def get_receipt(self, receipt_id: str) -> JiraSyncReceipt | None:
        self.initialize()
        row = self.connection.execute(
            "SELECT receipt_json FROM jira_sync_receipts WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
        return None if row is None else JiraSyncReceipt.model_validate_json(row[0])

    def list_outbox(
        self,
        states: Iterable[JiraOperationState] = (
            JiraOperationState.PLANNED,
            JiraOperationState.PENDING,
            JiraOperationState.FAILED,
            JiraOperationState.UNKNOWN_OUTCOME,
        ),
    ) -> tuple[dict[str, Any], ...]:
        self.initialize()
        selected = tuple(item.value for item in states)
        if not selected:
            return ()
        placeholders = ",".join("?" for _ in selected)
        rows = self.connection.execute(
            f"""
            SELECT operation_id, plan_id, operation_type, local_id, remote_key,
                   operation_state, idempotency_key, error_json, external_operation_id,
                   updated_at_utc
            FROM jira_sync_operations
            WHERE operation_state IN ({placeholders})
            ORDER BY updated_at_utc, operation_id
            """,
            selected,
        ).fetchall()
        return tuple(
            {
                "operation_id": row["operation_id"],
                "plan_id": row["plan_id"],
                "operation_type": row["operation_type"],
                "local_id": row["local_id"],
                "remote_key": row["remote_key"],
                "operation_state": row["operation_state"],
                "idempotency_key": row["idempotency_key"],
                "error": None if row["error_json"] is None else json.loads(row["error_json"]),
                "external_operation_id": row["external_operation_id"],
                "updated_at_utc": row["updated_at_utc"],
            }
            for row in rows
        )

    def status(self, project_key: str | None = None) -> dict[str, Any]:
        self.initialize()
        where = "" if project_key is None else " WHERE project_key = ?"
        params: tuple[Any, ...] = () if project_key is None else (project_key,)
        snapshots = self.connection.execute(
            f"SELECT COUNT(*) FROM jira_remote_snapshots{where}", params
        ).fetchone()[0]
        plans = self.connection.execute(
            f"SELECT COUNT(*) FROM jira_reconciliation_plans{where}", params
        ).fetchone()[0]
        mappings = self.connection.execute("SELECT COUNT(*) FROM jira_remote_mappings").fetchone()[
            0
        ]
        states = {
            row[0]: row[1]
            for row in self.connection.execute(
                "SELECT operation_state, COUNT(*) FROM jira_sync_operations GROUP BY operation_state"
            ).fetchall()
        }
        return {
            "schema_version": "1.0.0",
            "project_key": project_key,
            "snapshots": int(snapshots),
            "plans": int(plans),
            "mappings": int(mappings),
            "operation_states": dict(sorted(states.items())),
            "outbox": list(self.list_outbox()),
        }
