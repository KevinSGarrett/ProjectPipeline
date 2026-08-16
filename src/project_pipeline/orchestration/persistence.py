from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.domain.orchestration import (
    DurableOperation,
    DurableOperationState,
    DurableWait,
    OrchestrationStatus,
    RecoveryDecision,
    WorkerHeartbeat,
    WorkflowCheckpoint,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowState,
    canonical_payload_sha256,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class OrchestrationConflictError(RuntimeError):
    """Raised when durable state changed after the caller's observation."""


class OrchestrationStore:
    def __init__(self, database: Path | str, root: Path) -> None:
        self.root = root.resolve()
        self.database = database
        self.db = sqlite3.connect(str(database))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")

    def __enter__(self) -> OrchestrationStore:
        self.initialize()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def register_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        payload = definition.model_dump_json()
        with self.db:
            self.db.execute(
                """INSERT OR IGNORE INTO orchestration_workflow_definitions
                (definition_id, workflow_name, version, payload_json) VALUES (?, ?, ?, ?)""",
                (definition.definition_id, definition.workflow_name, definition.version, payload),
            )
            row = self.db.execute(
                "SELECT payload_json FROM orchestration_workflow_definitions WHERE definition_id = ?",
                (definition.definition_id,),
            ).fetchone()
        if row is None or str(row[0]) != payload:
            raise OrchestrationConflictError("workflow definition identity collision")
        return definition

    def get_definition(self, definition_id: str) -> WorkflowDefinition | None:
        row = self.db.execute(
            "SELECT payload_json FROM orchestration_workflow_definitions WHERE definition_id = ?",
            (definition_id,),
        ).fetchone()
        return WorkflowDefinition.model_validate_json(row[0]) if row else None

    def create_workflow(self, workflow: WorkflowInstance) -> WorkflowInstance:
        payload = workflow.model_dump_json()
        try:
            with self.db:
                self.db.execute(
                    """INSERT INTO orchestration_workflows
                    (workflow_id, definition_id, idempotency_key, state, row_version, backend,
                     backend_run_id, assigned_worker_id, payload_json, created_at_utc, updated_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        workflow.workflow_id,
                        workflow.definition_id,
                        workflow.idempotency_key,
                        workflow.state.value,
                        workflow.version,
                        workflow.backend.value,
                        workflow.backend_run_id,
                        workflow.assigned_worker_id,
                        payload,
                        workflow.created_at_utc.isoformat(),
                        workflow.updated_at_utc.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            existing = self.get_workflow(workflow.workflow_id)
            if existing == workflow:
                return existing
            raise OrchestrationConflictError(
                "workflow identity or idempotency collision"
            ) from error
        return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        row = self.db.execute(
            "SELECT payload_json FROM orchestration_workflows WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        return WorkflowInstance.model_validate_json(row[0]) if row else None

    def find_workflow_by_idempotency(
        self, definition_id: str, idempotency_key: str
    ) -> WorkflowInstance | None:
        row = self.db.execute(
            """SELECT payload_json FROM orchestration_workflows
            WHERE definition_id = ? AND idempotency_key = ?""",
            (definition_id, idempotency_key),
        ).fetchone()
        return WorkflowInstance.model_validate_json(row[0]) if row else None

    def update_workflow(
        self, workflow: WorkflowInstance, *, expected_version: int
    ) -> WorkflowInstance:
        if workflow.version != expected_version + 1:
            raise ValueError("updated workflow version must increment by exactly one")
        payload = workflow.model_dump_json()
        with self.db:
            cursor = self.db.execute(
                """UPDATE orchestration_workflows
                SET state = ?, row_version = ?, backend = ?, backend_run_id = ?,
                    assigned_worker_id = ?, payload_json = ?, updated_at_utc = ?
                WHERE workflow_id = ? AND row_version = ?""",
                (
                    workflow.state.value,
                    workflow.version,
                    workflow.backend.value,
                    workflow.backend_run_id,
                    workflow.assigned_worker_id,
                    payload,
                    workflow.updated_at_utc.isoformat(),
                    workflow.workflow_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise OrchestrationConflictError("workflow optimistic concurrency conflict")
        return workflow

    def next_event_sequence(self, workflow_id: str) -> int:
        row = self.db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM orchestration_events WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        return int(row[0])

    def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        with self.db:
            try:
                self.db.execute(
                    """INSERT INTO orchestration_events
                    (event_id, workflow_id, sequence, event_type, payload_json, occurred_at_utc, correlation_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.event_id,
                        event.workflow_id,
                        event.sequence,
                        event.event_type,
                        event.model_dump_json(),
                        event.occurred_at_utc.isoformat(),
                        event.correlation_id,
                    ),
                )
            except sqlite3.IntegrityError as error:
                row = self.db.execute(
                    "SELECT payload_json FROM orchestration_events WHERE event_id = ?",
                    (event.event_id,),
                ).fetchone()
                if row is not None and str(row[0]) == event.model_dump_json():
                    return event
                raise OrchestrationConflictError(
                    "workflow event sequence or identity collision"
                ) from error
        return event

    def events(self, workflow_id: str) -> tuple[WorkflowEvent, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM orchestration_events WHERE workflow_id = ? ORDER BY sequence",
            (workflow_id,),
        ).fetchall()
        return tuple(WorkflowEvent.model_validate_json(row[0]) for row in rows)

    def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> WorkflowCheckpoint:
        payload = checkpoint.model_dump_json()
        with self.db:
            self.db.execute(
                """INSERT OR IGNORE INTO orchestration_checkpoints
                (checkpoint_id, workflow_id, step_id, attempt, payload_sha256, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint.checkpoint_id,
                    checkpoint.workflow_id,
                    checkpoint.step_id,
                    checkpoint.attempt,
                    checkpoint.payload_sha256,
                    payload,
                    checkpoint.created_at_utc.isoformat(),
                ),
            )
            row = self.db.execute(
                "SELECT payload_json FROM orchestration_checkpoints WHERE checkpoint_id = ?",
                (checkpoint.checkpoint_id,),
            ).fetchone()
        if row is None or str(row[0]) != payload:
            raise OrchestrationConflictError("checkpoint identity collision")
        return checkpoint

    def latest_checkpoint(self, workflow_id: str) -> WorkflowCheckpoint | None:
        row = self.db.execute(
            """SELECT payload_json FROM orchestration_checkpoints
            WHERE workflow_id = ? ORDER BY created_at_utc DESC, checkpoint_id DESC LIMIT 1""",
            (workflow_id,),
        ).fetchone()
        return WorkflowCheckpoint.model_validate_json(row[0]) if row else None

    def save_wait(self, wait: DurableWait) -> DurableWait:
        payload = wait.model_dump_json()
        with self.db:
            self.db.execute(
                """INSERT INTO orchestration_waits
                (wait_id, workflow_id, kind, signal_name, release_at_utc, satisfied_at_utc, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(wait_id) DO UPDATE SET
                    satisfied_at_utc=excluded.satisfied_at_utc, payload_json=excluded.payload_json""",
                (
                    wait.wait_id,
                    wait.workflow_id,
                    wait.kind.value,
                    wait.signal_name,
                    wait.release_at_utc.isoformat() if wait.release_at_utc else None,
                    wait.satisfied_at_utc.isoformat() if wait.satisfied_at_utc else None,
                    payload,
                    wait.created_at_utc.isoformat(),
                ),
            )
        return wait

    def get_wait(self, wait_id: str) -> DurableWait | None:
        row = self.db.execute(
            "SELECT payload_json FROM orchestration_waits WHERE wait_id = ?",
            (wait_id,),
        ).fetchone()
        return DurableWait.model_validate_json(row[0]) if row else None

    def due_waits(self, now: datetime) -> tuple[DurableWait, ...]:
        rows = self.db.execute(
            """SELECT payload_json FROM orchestration_waits
            WHERE satisfied_at_utc IS NULL AND release_at_utc IS NOT NULL AND release_at_utc <= ?
            ORDER BY release_at_utc, wait_id""",
            (now.astimezone(UTC).isoformat(),),
        ).fetchall()
        return tuple(DurableWait.model_validate_json(row[0]) for row in rows)

    def save_worker_heartbeat(self, heartbeat: WorkerHeartbeat) -> WorkerHeartbeat:
        current = self.db.execute(
            "SELECT fencing_epoch FROM orchestration_workers WHERE worker_id = ?",
            (heartbeat.worker_id,),
        ).fetchone()
        if current is not None and heartbeat.fencing_epoch < int(current[0]):
            raise OrchestrationConflictError("stale worker fencing epoch")
        with self.db:
            self.db.execute(
                """INSERT INTO orchestration_workers
                (worker_id, fencing_epoch, payload_json, observed_at_utc, expires_at_utc)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    fencing_epoch=excluded.fencing_epoch,
                    payload_json=excluded.payload_json,
                    observed_at_utc=excluded.observed_at_utc,
                    expires_at_utc=excluded.expires_at_utc""",
                (
                    heartbeat.worker_id,
                    heartbeat.fencing_epoch,
                    heartbeat.model_dump_json(),
                    heartbeat.observed_at_utc.isoformat(),
                    heartbeat.expires_at_utc.isoformat(),
                ),
            )
        return heartbeat

    def worker(self, worker_id: str) -> WorkerHeartbeat | None:
        row = self.db.execute(
            "SELECT payload_json FROM orchestration_workers WHERE worker_id = ?",
            (worker_id,),
        ).fetchone()
        return WorkerHeartbeat.model_validate_json(row[0]) if row else None

    def stale_workers(self, now: datetime) -> tuple[WorkerHeartbeat, ...]:
        rows = self.db.execute(
            """SELECT payload_json FROM orchestration_workers
            WHERE expires_at_utc <= ? ORDER BY expires_at_utc, worker_id""",
            (now.astimezone(UTC).isoformat(),),
        ).fetchall()
        return tuple(WorkerHeartbeat.model_validate_json(row[0]) for row in rows)

    def workflows_for_worker(self, worker_id: str) -> tuple[WorkflowInstance, ...]:
        rows = self.db.execute(
            """SELECT payload_json FROM orchestration_workflows
            WHERE assigned_worker_id = ? AND state IN ('RUNNING','WAITING','RETRY_SCHEDULED','CANCEL_REQUESTED')
            ORDER BY workflow_id""",
            (worker_id,),
        ).fetchall()
        return tuple(WorkflowInstance.model_validate_json(row[0]) for row in rows)

    def record_inbox(
        self,
        *,
        message_id: str,
        workflow_id: str,
        message_type: str,
        payload: dict[str, Any],
        received_at_utc: datetime,
    ) -> bool:
        payload_sha = canonical_payload_sha256(payload)
        payload_json = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        with self.db:
            cursor = self.db.execute(
                """INSERT OR IGNORE INTO orchestration_inbox
                (message_id, workflow_id, message_type, payload_sha256, payload_json, received_at_utc)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    workflow_id,
                    message_type,
                    payload_sha,
                    payload_json,
                    received_at_utc.astimezone(UTC).isoformat(),
                ),
            )
            if cursor.rowcount == 0:
                row = self.db.execute(
                    "SELECT payload_sha256 FROM orchestration_inbox WHERE message_id = ?",
                    (message_id,),
                ).fetchone()
                if row is None or str(row[0]) != payload_sha:
                    raise OrchestrationConflictError("inbox message identity collision")
                return False
        return True

    def save_operation(self, operation: DurableOperation) -> DurableOperation:
        payload = operation.model_dump_json()
        with self.db:
            self.db.execute(
                """INSERT INTO orchestration_outbox
                (operation_id, workflow_id, operation_type, idempotency_key, state, payload_sha256,
                 payload_json, backend, backend_operation_id, attempt_count, last_error, created_at_utc, updated_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(operation_id) DO UPDATE SET
                    state=excluded.state, payload_json=excluded.payload_json,
                    backend_operation_id=excluded.backend_operation_id,
                    attempt_count=excluded.attempt_count, last_error=excluded.last_error,
                    updated_at_utc=excluded.updated_at_utc""",
                (
                    operation.operation_id,
                    operation.workflow_id,
                    operation.operation_type,
                    operation.idempotency_key,
                    operation.state.value,
                    operation.payload_sha256,
                    payload,
                    operation.backend.value,
                    operation.backend_operation_id,
                    operation.attempt_count,
                    operation.last_error,
                    operation.created_at_utc.isoformat(),
                    operation.updated_at_utc.isoformat(),
                ),
            )
        return operation

    def get_operation(self, operation_id: str) -> DurableOperation | None:
        row = self.db.execute(
            "SELECT payload_json FROM orchestration_outbox WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return DurableOperation.model_validate_json(row[0]) if row else None

    def operations_by_state(self, state: DurableOperationState) -> tuple[DurableOperation, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM orchestration_outbox WHERE state = ? ORDER BY created_at_utc, operation_id",
            (state.value,),
        ).fetchall()
        return tuple(DurableOperation.model_validate_json(row[0]) for row in rows)

    def save_recovery_decision(self, decision: RecoveryDecision) -> RecoveryDecision:
        payload = decision.model_dump_json()
        with self.db:
            self.db.execute(
                """INSERT OR IGNORE INTO orchestration_recovery_decisions
                (recovery_id, workflow_id, action, safe_to_automate, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    decision.recovery_id,
                    decision.workflow_id,
                    decision.action.value,
                    int(decision.safe_to_automate),
                    payload,
                    decision.created_at_utc.isoformat(),
                ),
            )
        return decision

    def recovery_decisions(self, workflow_id: str) -> tuple[RecoveryDecision, ...]:
        rows = self.db.execute(
            """SELECT payload_json FROM orchestration_recovery_decisions
            WHERE workflow_id = ? ORDER BY created_at_utc, recovery_id""",
            (workflow_id,),
        ).fetchall()
        return tuple(RecoveryDecision.model_validate_json(row[0]) for row in rows)

    def workflows_in_states(
        self, states: tuple[WorkflowState, ...]
    ) -> tuple[WorkflowInstance, ...]:
        if not states:
            return ()
        placeholders = ",".join("?" for _ in states)
        rows = self.db.execute(
            f"SELECT payload_json FROM orchestration_workflows WHERE state IN ({placeholders}) ORDER BY workflow_id",
            tuple(item.value for item in states),
        ).fetchall()
        return tuple(WorkflowInstance.model_validate_json(row[0]) for row in rows)

    def status(self, *, now: datetime | None = None) -> OrchestrationStatus:
        current = (now or datetime.now(UTC)).astimezone(UTC)

        def scalar(sql: str, args: tuple[object, ...] = ()) -> int:
            return int(self.db.execute(sql, args).fetchone()[0])

        return OrchestrationStatus(
            definitions=scalar("SELECT COUNT(*) FROM orchestration_workflow_definitions"),
            workflows=scalar("SELECT COUNT(*) FROM orchestration_workflows"),
            active_workflows=scalar(
                "SELECT COUNT(*) FROM orchestration_workflows WHERE state IN ('PENDING','RUNNING','WAITING','RETRY_SCHEDULED','SUSPENDED','RECOVERY_REQUIRED','CANCEL_REQUESTED')"
            ),
            waiting_workflows=scalar(
                "SELECT COUNT(*) FROM orchestration_workflows WHERE state = 'WAITING'"
            ),
            recovery_required=scalar(
                "SELECT COUNT(*) FROM orchestration_workflows WHERE state = 'RECOVERY_REQUIRED'"
            ),
            unknown_outcomes=scalar(
                "SELECT COUNT(*) FROM orchestration_outbox WHERE state = ?",
                (DurableOperationState.UNKNOWN_OUTCOME.value,),
            ),
            stale_workers=scalar(
                "SELECT COUNT(*) FROM orchestration_workers WHERE expires_at_utc <= ?",
                (current.isoformat(),),
            ),
        )
