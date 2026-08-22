from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Any

from project_pipeline.domain.github import (
    GitHubOperation,
    GitHubOperationReceipt,
    GitOperationState,
    MergeGateDecision,
    ResourceOwnershipClaim,
)
from project_pipeline.github_steward.errors import GitHubStewardError
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class GitHubStewardStore:
    def __init__(self, database: Path | str, root: Path) -> None:
        self.database = database
        self.root = root.resolve()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> GitHubStewardStore:
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("store is not open")
        return self.connection

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def save_ownership(self, claim: ResourceOwnershipClaim) -> None:
        self.db.execute(
            """
            INSERT INTO github_resource_ownership
                (ownership_id, repository_slug, resource_kind, resource, owner_task_id,
                 workspace_id, state, payload_json, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ownership_id) DO UPDATE SET
                state=excluded.state, payload_json=excluded.payload_json,
                updated_at_utc=excluded.updated_at_utc
            """,
            (
                claim.ownership_id,
                claim.repository_slug,
                claim.resource_kind.value,
                claim.resource,
                claim.owner_task_id,
                claim.workspace_id,
                claim.state.value,
                claim.model_dump_json(),
                claim.acquired_at_utc.isoformat(),
            ),
        )
        self.db.commit()

    def active_ownership(self, repository_slug: str) -> tuple[ResourceOwnershipClaim, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM github_resource_ownership WHERE repository_slug=? AND state='ACTIVE' ORDER BY ownership_id",
            (repository_slug,),
        ).fetchall()
        return tuple(ResourceOwnershipClaim.model_validate_json(row[0]) for row in rows)

    def save_gate(self, gate: MergeGateDecision) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO github_merge_gate_evaluations
                (gate_id, repository_slug, pull_number, head_sha, state, payload_json, evaluated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gate.gate_id,
                gate.repository_slug,
                gate.pull_number,
                gate.head_sha,
                gate.state.value,
                gate.model_dump_json(),
                gate.evaluated_at_utc.isoformat(),
            ),
        )
        self.db.commit()

    def save_operation(self, operation: GitHubOperation) -> None:
        existing = self.get_operation(operation.operation_id)
        if (
            existing is not None
            and existing.state is GitOperationState.UNKNOWN_OUTCOME
            and operation.state in {GitOperationState.PLANNED, GitOperationState.PENDING}
        ):
            raise GitHubStewardError(
                "unknown-outcome operations must be reconciled before any retry"
            )
        self.db.execute(
            """
            INSERT INTO github_operations
                (operation_id, operation_type, repository_slug, target, request_fingerprint,
                 idempotency_key, state, expected_head_sha, authorization_id, actor_id,
                 correlation_id, payload_json, observed_result_json, created_at_utc, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_id) DO UPDATE SET
                state=excluded.state, authorization_id=excluded.authorization_id,
                observed_result_json=excluded.observed_result_json,
                updated_at_utc=excluded.updated_at_utc
            """,
            (
                operation.operation_id,
                operation.operation_type.value,
                operation.repository_slug,
                operation.target,
                operation.request_fingerprint,
                operation.idempotency_key,
                operation.state.value,
                operation.expected_head_sha,
                operation.authorization_id,
                operation.actor_id,
                operation.correlation_id,
                json.dumps(operation.payload, sort_keys=True),
                json.dumps(operation.observed_result, sort_keys=True)
                if operation.observed_result is not None
                else None,
                operation.created_at_utc.isoformat(),
                operation.updated_at_utc.isoformat(),
            ),
        )
        self.db.commit()

    def get_operation(self, operation_id: str) -> GitHubOperation | None:
        row = self.db.execute(
            "SELECT * FROM github_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if row is None:
            return None
        return GitHubOperation(
            operation_id=row["operation_id"],
            operation_type=row["operation_type"],
            repository_slug=row["repository_slug"],
            target=row["target"],
            request_fingerprint=row["request_fingerprint"],
            idempotency_key=row["idempotency_key"],
            state=row["state"],
            expected_head_sha=row["expected_head_sha"],
            authorization_id=row["authorization_id"],
            actor_id=row["actor_id"],
            correlation_id=row["correlation_id"],
            payload=json.loads(row["payload_json"]),
            observed_result=json.loads(row["observed_result_json"])
            if row["observed_result_json"]
            else None,
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )

    def pending_operations(self, repository_slug: str) -> tuple[GitHubOperation, ...]:
        rows = self.db.execute(
            "SELECT operation_id FROM github_operations WHERE repository_slug=? AND state IN ('PLANNED','PENDING','UNKNOWN_OUTCOME') ORDER BY created_at_utc, operation_id",
            (repository_slug,),
        ).fetchall()
        return tuple(item for row in rows if (item := self.get_operation(row[0])) is not None)

    def save_receipt(self, receipt: GitHubOperationReceipt) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO github_operation_receipts (receipt_id, operation_id, state, payload_json, created_at_utc) VALUES (?, ?, ?, ?, ?)",
            (
                receipt.receipt_id,
                receipt.operation_id,
                receipt.state.value,
                receipt.model_dump_json(),
                receipt.created_at_utc.isoformat(),
            ),
        )
        self.db.commit()

    def status(self, repository_slug: str) -> dict[str, Any]:
        counts = {
            row[0]: row[1]
            for row in self.db.execute(
                "SELECT state, COUNT(*) FROM github_operations WHERE repository_slug=? GROUP BY state",
                (repository_slug,),
            ).fetchall()
        }
        ownership = self.db.execute(
            "SELECT COUNT(*) FROM github_resource_ownership WHERE repository_slug=? AND state='ACTIVE'",
            (repository_slug,),
        ).fetchone()[0]
        gates = self.db.execute(
            "SELECT COUNT(*) FROM github_merge_gate_evaluations WHERE repository_slug=?",
            (repository_slug,),
        ).fetchone()[0]
        return {
            "repository_slug": repository_slug,
            "operation_counts": dict(sorted(counts.items())),
            "active_ownership": ownership,
            "merge_gate_evaluations": gates,
            "reconciliation_required": counts.get(GitOperationState.UNKNOWN_OUTCOME.value, 0) > 0,
        }
