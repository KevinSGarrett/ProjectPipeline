from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.domain import (
    BootstrapReceipt,
    CompiledProjectManifest,
    DomainStateTransition,
    IdentifierKind,
    ProjectLifecycleState,
    ProjectManifest,
    ProjectStateRecord,
    RequirementRecord,
    TaskLifecycleState,
    TaskStateRecord,
    TraceabilityAuthority,
    TraceabilityLink,
    TraceabilityLinkType,
    TraceabilityMutation,
    TraceabilityMutationResult,
    deterministic_identifier,
    ensure_project_transition,
    ensure_task_transition,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class PersistenceError(RuntimeError):
    """Base failure for deterministic persistence operations."""


class ConcurrentStateChangeError(PersistenceError):
    """Raised when optimistic concurrency detects a stale write."""


class MissingStateError(PersistenceError):
    """Raised when requested canonical state has not been persisted."""


_LINK_FIELDS: dict[TraceabilityLinkType, str] = {
    TraceabilityLinkType.SOURCE: "source_references",
    TraceabilityLinkType.PLAN: "plan_ids",
    TraceabilityLinkType.PLAN_SECTION: "plan_section_ids",
    TraceabilityLinkType.JIRA: "jira_ids",
    TraceabilityLinkType.IMPLEMENTATION: "implementation_paths",
    TraceabilityLinkType.TEST: "test_ids",
    TraceabilityLinkType.EVIDENCE: "evidence_ids",
    TraceabilityLinkType.DECISION: "decision_ids",
    TraceabilityLinkType.OPEN_DECISION: "open_decision_ids",
    TraceabilityLinkType.EVOLUTION: "evolution_ids",
}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteStateStore:
    """Deterministic local persistence profile implementing production-facing ports."""

    def __init__(self, database_path: Path | str, repository_root: Path) -> None:
        self.database_path = database_path
        self.repository_root = repository_root.resolve()
        if database_path != ":memory:":
            path = Path(database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(database_path), isolation_level=None, timeout=30.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 30000")

    def __enter__(self) -> SQLiteStateStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self.connection.in_transaction:
            raise PersistenceError("nested store transactions are not supported")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.connection, self.repository_root).apply_all()

    def migration_status(self) -> dict[str, Any]:
        return SQLiteMigrationRunner(self.connection, self.repository_root).status().as_dict()

    def put_project_manifest(self, manifest: ProjectManifest) -> None:
        document = manifest.model_dump(mode="json")
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    project_id, project_name, manifest_revision, manifest_fingerprint,
                    manifest_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    project_name = excluded.project_name,
                    manifest_revision = excluded.manifest_revision,
                    manifest_fingerprint = excluded.manifest_fingerprint,
                    manifest_json = excluded.manifest_json,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    manifest.project_id,
                    manifest.project_name,
                    manifest.revision,
                    manifest.semantic_fingerprint(),
                    _json(document),
                    manifest.created_at_utc.isoformat(),
                    manifest.updated_at_utc.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO project_states (
                    project_id, state, version, manifest_revision, blocked_reason,
                    task_counts_json, last_transition_id, updated_at_utc
                ) VALUES (?, ?, 1, ?, NULL, ?, NULL, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    manifest_revision = excluded.manifest_revision,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    manifest.project_id,
                    ProjectLifecycleState.REGISTERED.value,
                    manifest.revision,
                    _json({}),
                    manifest.updated_at_utc.isoformat(),
                ),
            )

    def get_project_manifest(self, project_id: str) -> ProjectManifest | None:
        row = self.connection.execute(
            "SELECT manifest_json FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return None if row is None else ProjectManifest.model_validate_json(row[0])

    def get_project_state(self, project_id: str) -> ProjectStateRecord | None:
        row = self.connection.execute(
            "SELECT * FROM project_states WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        return ProjectStateRecord(
            project_id=row["project_id"],
            state=row["state"],
            version=row["version"],
            manifest_revision=row["manifest_revision"],
            blocked_reason=row["blocked_reason"],
            task_counts=json.loads(row["task_counts_json"]),
            last_transition_id=row["last_transition_id"],
            updated_at_utc=row["updated_at_utc"],
        )

    def transition_project(
        self,
        *,
        project_id: str,
        next_state: ProjectLifecycleState,
        expected_version: int,
        reason: str,
        actor_id: str,
        correlation_id: str,
        blocked_reason: str | None = None,
    ) -> ProjectStateRecord:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM project_states WHERE project_id = ?", (project_id,)
            ).fetchone()
            if row is None:
                raise MissingStateError(f"project state does not exist: {project_id}")
            if row["version"] != expected_version:
                raise ConcurrentStateChangeError(
                    f"project version mismatch: expected {expected_version}, observed {row['version']}"
                )
            previous = ProjectLifecycleState(row["state"])
            ensure_project_transition(previous, next_state)
            if next_state is ProjectLifecycleState.BLOCKED and not blocked_reason:
                raise ValueError("blocked project transition requires blocked_reason")
            if next_state is not ProjectLifecycleState.BLOCKED and blocked_reason:
                raise ValueError("blocked_reason is only valid for a BLOCKED project")
            transition = DomainStateTransition.create(
                entity_type="project",
                entity_id=project_id,
                previous_state=previous.value,
                next_state=next_state.value,
                expected_version=expected_version,
                reason=reason,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            timestamp = transition.occurred_at_utc.isoformat()
            updated = connection.execute(
                """
                UPDATE project_states
                SET state = ?, version = ?, blocked_reason = ?,
                    last_transition_id = ?, updated_at_utc = ?
                WHERE project_id = ? AND version = ?
                """,
                (
                    next_state.value,
                    transition.resulting_version,
                    blocked_reason,
                    transition.transition_id,
                    timestamp,
                    project_id,
                    expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise ConcurrentStateChangeError("project state changed during transition")
            self._insert_transition(connection, project_id, transition)
        result = self.get_project_state(project_id)
        if result is None:
            raise PersistenceError("project state disappeared after transition")
        return result

    def put_task_states(self, tasks: Iterable[TaskStateRecord]) -> int:
        rows = list(tasks)
        with self.transaction() as connection:
            for task in rows:
                connection.execute(
                    """
                    INSERT INTO task_states (
                        task_id, project_id, state, version, priority,
                        dependency_ids_json, blocker_ids_json, owner_id,
                        blocked_reason, last_transition_id, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO NOTHING
                    """,
                    (
                        task.task_id,
                        task.project_id,
                        task.state.value,
                        task.version,
                        task.priority,
                        _json(list(task.dependency_ids)),
                        _json(list(task.blocker_ids)),
                        task.owner_id,
                        task.blocked_reason,
                        task.last_transition_id,
                        task.updated_at_utc.isoformat(),
                    ),
                )
        return len(rows)

    def get_task_state(self, task_id: str) -> TaskStateRecord | None:
        row = self.connection.execute(
            "SELECT * FROM task_states WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return TaskStateRecord(
            task_id=row["task_id"],
            project_id=row["project_id"],
            state=row["state"],
            version=row["version"],
            priority=row["priority"],
            dependency_ids=tuple(json.loads(row["dependency_ids_json"])),
            blocker_ids=tuple(json.loads(row["blocker_ids_json"])),
            owner_id=row["owner_id"],
            blocked_reason=row["blocked_reason"],
            last_transition_id=row["last_transition_id"],
            updated_at_utc=row["updated_at_utc"],
        )

    def list_task_states(self, project_id: str) -> tuple[TaskStateRecord, ...]:
        rows = self.connection.execute(
            "SELECT task_id FROM task_states WHERE project_id = ? ORDER BY task_id",
            (project_id,),
        ).fetchall()
        return tuple(
            state for row in rows if (state := self.get_task_state(str(row["task_id"]))) is not None
        )

    def transition_task(
        self,
        *,
        task_id: str,
        next_state: TaskLifecycleState,
        expected_version: int,
        reason: str,
        actor_id: str,
        correlation_id: str,
        blocked_reason: str | None = None,
        owner_id: str | None = None,
    ) -> TaskStateRecord:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM task_states WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise MissingStateError(f"task state does not exist: {task_id}")
            if row["version"] != expected_version:
                raise ConcurrentStateChangeError(
                    f"task version mismatch: expected {expected_version}, observed {row['version']}"
                )
            previous = TaskLifecycleState(row["state"])
            ensure_task_transition(previous, next_state)
            if next_state is TaskLifecycleState.BLOCKED and not blocked_reason:
                raise ValueError("blocked task transition requires blocked_reason")
            if next_state is not TaskLifecycleState.BLOCKED and blocked_reason:
                raise ValueError("blocked_reason is only valid for a BLOCKED task")
            transition = DomainStateTransition.create(
                entity_type="task",
                entity_id=task_id,
                previous_state=previous.value,
                next_state=next_state.value,
                expected_version=expected_version,
                reason=reason,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            timestamp = transition.occurred_at_utc.isoformat()
            updated = connection.execute(
                """
                UPDATE task_states
                SET state = ?, version = ?, owner_id = ?, blocked_reason = ?,
                    last_transition_id = ?, updated_at_utc = ?
                WHERE task_id = ? AND version = ?
                """,
                (
                    next_state.value,
                    transition.resulting_version,
                    owner_id if owner_id is not None else row["owner_id"],
                    blocked_reason,
                    transition.transition_id,
                    timestamp,
                    task_id,
                    expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise ConcurrentStateChangeError("task state changed during transition")
            self._insert_transition(connection, row["project_id"], transition)
        result = self.get_task_state(task_id)
        if result is None:
            raise PersistenceError("task state disappeared after transition")
        return result

    def _insert_transition(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        transition: DomainStateTransition,
    ) -> None:
        connection.execute(
            """
            INSERT INTO state_transitions (
                transition_id, project_id, entity_type, entity_id, previous_state,
                next_state, expected_version, resulting_version, reason, actor_id,
                correlation_id, occurred_at_utc, transition_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition.transition_id,
                project_id,
                transition.entity_type,
                transition.entity_id,
                transition.previous_state,
                transition.next_state,
                transition.expected_version,
                transition.resulting_version,
                transition.reason,
                transition.actor_id,
                transition.correlation_id,
                transition.occurred_at_utc.isoformat(),
                _json(transition.model_dump(mode="json")),
            ),
        )

    def list_transitions(
        self, *, entity_type: str, entity_id: str
    ) -> tuple[DomainStateTransition, ...]:
        rows = self.connection.execute(
            """
            SELECT transition_json FROM state_transitions
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY resulting_version
            """,
            (entity_type, entity_id),
        ).fetchall()
        return tuple(DomainStateTransition.model_validate_json(row[0]) for row in rows)

    def import_requirements(
        self,
        requirements: Iterable[RequirementRecord],
        *,
        source_path: str,
        catalog_sha256: str,
    ) -> dict[str, int | str]:
        records = list(requirements)
        identifiers = [item.requirement_id for item in records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("requirement import contains duplicate identifiers")
        links = [link for item in records for link in links_from_requirement(item)]
        imported_at = _now()
        import_id = deterministic_identifier(
            IdentifierKind.CATALOG_IMPORT, source_path, catalog_sha256
        ).value
        with self.transaction() as connection:
            existing = {
                str(row["requirement_id"]): row
                for row in connection.execute(
                    "SELECT requirement_id, revision, record_json FROM requirements"
                ).fetchall()
            }
            for item in records:
                document = _json(item.as_registry_row())
                old = existing.get(item.requirement_id)
                revision = 1 if old is None else int(old["revision"])
                if old is not None and old["record_json"] != document:
                    revision += 1
                connection.execute(
                    """
                    INSERT INTO requirements (
                        requirement_id, domain, title, statement, implementation_state,
                        disposition, priority, risk, revision, record_json, imported_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(requirement_id) DO UPDATE SET
                        domain = excluded.domain,
                        title = excluded.title,
                        statement = excluded.statement,
                        implementation_state = excluded.implementation_state,
                        disposition = excluded.disposition,
                        priority = excluded.priority,
                        risk = excluded.risk,
                        revision = excluded.revision,
                        record_json = excluded.record_json,
                        imported_at_utc = excluded.imported_at_utc
                    """,
                    (
                        item.requirement_id,
                        item.domain,
                        item.title,
                        item.statement,
                        item.implementation_state.value,
                        item.disposition.value,
                        item.priority,
                        item.risk,
                        revision,
                        document,
                        imported_at,
                    ),
                )
                connection.execute(
                    "DELETE FROM traceability_links WHERE requirement_id = ?",
                    (item.requirement_id,),
                )
            if identifiers:
                placeholders = ",".join("?" for _ in identifiers)
                connection.execute(
                    f"DELETE FROM requirements WHERE requirement_id NOT IN ({placeholders})",
                    identifiers,
                )
            else:
                connection.execute("DELETE FROM requirements")
            for link in links:
                self._insert_link(connection, link)
            connection.execute(
                """
                INSERT INTO catalog_imports (
                    import_id, catalog_sha256, requirement_count, link_count,
                    imported_at_utc, source_path
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(catalog_sha256, source_path) DO UPDATE SET
                    requirement_count = excluded.requirement_count,
                    link_count = excluded.link_count,
                    imported_at_utc = excluded.imported_at_utc
                """,
                (
                    import_id,
                    catalog_sha256,
                    len(records),
                    len(links),
                    imported_at,
                    source_path,
                ),
            )
        return {
            "schema_version": "1.0.0",
            "import_id": import_id,
            "requirement_count": len(records),
            "link_count": len(links),
            "catalog_sha256": catalog_sha256,
        }

    def _insert_link(self, connection: sqlite3.Connection, link: TraceabilityLink) -> None:
        connection.execute(
            """
            INSERT INTO traceability_links (
                link_id, requirement_id, link_type, target, ordinal,
                authority, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link.link_id,
                link.requirement_id,
                link.link_type.value,
                link.target,
                link.ordinal,
                link.authority.value,
                _json(link.metadata),
            ),
        )

    def get_requirement(self, requirement_id: str) -> RequirementRecord | None:
        row = self.connection.execute(
            "SELECT record_json FROM requirements WHERE requirement_id = ?",
            (requirement_id,),
        ).fetchone()
        return None if row is None else RequirementRecord.model_validate_json(row[0])

    def requirement_revision(self, requirement_id: str) -> int | None:
        row = self.connection.execute(
            "SELECT revision FROM requirements WHERE requirement_id = ?",
            (requirement_id,),
        ).fetchone()
        return None if row is None else int(row[0])

    def list_requirements(
        self,
        *,
        domain: str | None = None,
        implementation_state: str | None = None,
    ) -> tuple[RequirementRecord, ...]:
        query = "SELECT record_json FROM requirements WHERE 1 = 1"
        parameters: list[str] = []
        if domain:
            query += " AND domain = ?"
            parameters.append(domain.upper())
        if implementation_state:
            query += " AND implementation_state = ?"
            parameters.append(implementation_state)
        query += " ORDER BY requirement_id"
        rows = self.connection.execute(query, parameters).fetchall()
        return tuple(RequirementRecord.model_validate_json(row[0]) for row in rows)

    def list_requirement_links(self, requirement_id: str) -> tuple[TraceabilityLink, ...]:
        rows = self.connection.execute(
            """
            SELECT * FROM traceability_links
            WHERE requirement_id = ?
            ORDER BY link_type, ordinal, target, authority
            """,
            (requirement_id,),
        ).fetchall()
        return tuple(_link_from_row(row) for row in rows)

    def requirements_for_target(
        self, link_type: TraceabilityLinkType, target: str
    ) -> tuple[str, ...]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT requirement_id FROM traceability_links
            WHERE link_type = ? AND target = ?
            ORDER BY requirement_id
            """,
            (link_type.value, target),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def apply_traceability_mutation(
        self, mutation: TraceabilityMutation
    ) -> TraceabilityMutationResult:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT revision, record_json FROM requirements WHERE requirement_id = ?",
                (mutation.requirement_id,),
            ).fetchone()
            if row is None:
                raise MissingStateError(f"requirement does not exist: {mutation.requirement_id}")
            observed_revision = int(row["revision"])
            if observed_revision != mutation.expected_revision:
                raise ConcurrentStateChangeError(
                    f"requirement revision mismatch: expected {mutation.expected_revision}, "
                    f"observed {observed_revision}"
                )
            record = RequirementRecord.model_validate_json(row["record_json"])
            field = _LINK_FIELDS[mutation.link_type]
            document = record.as_registry_row()
            raw_values = document.get(field, [])
            values = list(raw_values) if isinstance(raw_values, (list, tuple)) else []
            changed = False
            if mutation.operation == "ADD" and mutation.target not in values:
                values.append(mutation.target)
                changed = True
            elif mutation.operation == "REMOVE" and mutation.target in values:
                values.remove(mutation.target)
                changed = True
            document[field] = values
            updated_record = RequirementRecord.model_validate(document)
            resulting_revision = observed_revision + (1 if changed else 0)
            link = TraceabilityLink.create(
                requirement_id=mutation.requirement_id,
                link_type=mutation.link_type,
                target=mutation.target,
                ordinal=values.index(mutation.target) if mutation.target in values else 0,
                authority=TraceabilityAuthority.PROPOSED_CHANGE,
                metadata={"operation": mutation.operation, "reason": mutation.reason},
            )
            if changed:
                connection.execute(
                    """
                    UPDATE requirements
                    SET record_json = ?, revision = ?, imported_at_utc = ?
                    WHERE requirement_id = ? AND revision = ?
                    """,
                    (
                        _json(updated_record.as_registry_row()),
                        resulting_revision,
                        _now(),
                        mutation.requirement_id,
                        observed_revision,
                    ),
                )
                connection.execute(
                    "DELETE FROM traceability_links WHERE requirement_id = ?",
                    (mutation.requirement_id,),
                )
                for current in links_from_requirement(
                    updated_record, authority=TraceabilityAuthority.PERSISTED_PROJECTION
                ):
                    self._insert_link(connection, current)
            mutation_id = deterministic_identifier(
                IdentifierKind.MUTATION,
                mutation.requirement_id,
                mutation.operation,
                mutation.link_type.value,
                mutation.target,
                str(observed_revision),
                mutation.actor_id,
                mutation.correlation_id,
            ).value
            connection.execute(
                """
                INSERT INTO traceability_mutations (
                    mutation_id, requirement_id, operation, link_type, target,
                    previous_revision, resulting_revision, changed, actor_id,
                    correlation_id, reason, recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation_id,
                    mutation.requirement_id,
                    mutation.operation,
                    mutation.link_type.value,
                    mutation.target,
                    observed_revision,
                    resulting_revision,
                    int(changed),
                    mutation.actor_id,
                    mutation.correlation_id,
                    mutation.reason,
                    _now(),
                ),
            )
        return TraceabilityMutationResult(
            mutation_id=mutation_id,
            requirement_id=mutation.requirement_id,
            operation=mutation.operation,
            link=link,
            previous_revision=observed_revision,
            resulting_revision=resulting_revision,
            changed=changed,
        )

    def export_requirement_projection(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.as_registry_row() for item in self.list_requirements())

    def verify_requirement_equivalence(
        self, requirements: Iterable[RequirementRecord]
    ) -> list[str]:
        expected = {item.requirement_id: item.as_registry_row() for item in requirements}
        observed = {
            item.requirement_id: item.as_registry_row() for item in self.list_requirements()
        }
        errors: list[str] = []
        for missing in sorted(expected.keys() - observed.keys()):
            errors.append(f"persisted requirement is missing: {missing}")
        for extra in sorted(observed.keys() - expected.keys()):
            errors.append(f"unexpected persisted requirement: {extra}")
        for common in sorted(expected.keys() & observed.keys()):
            if expected[common] != observed[common]:
                errors.append(f"persisted requirement differs from catalog: {common}")
        return errors

    def put_intake_compilation(
        self,
        manifest: CompiledProjectManifest,
        *,
        actor_id: str,
        correlation_id: str,
    ) -> dict[str, str | bool]:
        document = manifest.model_dump(mode="json")
        semantic_fingerprint = manifest.semantic_fingerprint()
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT semantic_fingerprint FROM intake_compilations WHERE compilation_id = ?",
                (manifest.compilation_id,),
            ).fetchone()
            if existing is not None:
                if existing["semantic_fingerprint"] != semantic_fingerprint:
                    raise PersistenceError(
                        "intake compilation identity is already associated with different semantics"
                    )
                return {
                    "compilation_id": manifest.compilation_id,
                    "changed": False,
                    "semantic_fingerprint": semantic_fingerprint,
                }
            connection.execute(
                """
                INSERT INTO intake_compilations (
                    compilation_id, project_id, project_name, intake_mode, adoption_stage,
                    target_root, repository_fingerprint, request_fingerprint,
                    semantic_fingerprint, manifest_json, compiled_at_utc, actor_id, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.compilation_id,
                    manifest.project_id,
                    manifest.project_name,
                    manifest.intake_mode.value,
                    manifest.adoption_stage.value,
                    manifest.target_root,
                    manifest.repository_map.fingerprint,
                    manifest.request_fingerprint,
                    semantic_fingerprint,
                    _json(document),
                    manifest.compiled_at_utc.isoformat(),
                    actor_id,
                    correlation_id,
                ),
            )
        return {
            "compilation_id": manifest.compilation_id,
            "changed": True,
            "semantic_fingerprint": semantic_fingerprint,
        }

    def get_intake_compilation(self, compilation_id: str) -> CompiledProjectManifest | None:
        row = self.connection.execute(
            "SELECT manifest_json FROM intake_compilations WHERE compilation_id = ?",
            (compilation_id,),
        ).fetchone()
        return (
            None
            if row is None
            else CompiledProjectManifest.model_validate_json(row["manifest_json"])
        )

    def list_intake_compilations(
        self, project_id: str | None = None
    ) -> tuple[CompiledProjectManifest, ...]:
        if project_id is None:
            rows = self.connection.execute(
                "SELECT manifest_json FROM intake_compilations ORDER BY compiled_at_utc, compilation_id"
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT manifest_json FROM intake_compilations
                WHERE project_id = ? ORDER BY compiled_at_utc, compilation_id
                """,
                (project_id,),
            ).fetchall()
        return tuple(
            CompiledProjectManifest.model_validate_json(row["manifest_json"]) for row in rows
        )

    def put_bootstrap_receipt(self, receipt: BootstrapReceipt) -> dict[str, str | bool]:
        document = receipt.model_dump(mode="json")
        semantic = {key: value for key, value in document.items() if key != "recorded_at_utc"}
        receipt_digest = hashlib.sha256(_json(semantic).encode("utf-8")).hexdigest()[:20].upper()
        receipt_id = f"RCPT-{receipt_digest}"
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT receipt_json FROM bootstrap_receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if existing is not None:
                observed = BootstrapReceipt.model_validate_json(existing["receipt_json"])
                observed_semantic = observed.model_dump(mode="json", exclude={"recorded_at_utc"})
                if observed_semantic != semantic:
                    raise PersistenceError(
                        "bootstrap receipt identity is associated with different semantics"
                    )
                return {"receipt_id": receipt_id, "changed": False}
            connection.execute(
                """
                INSERT INTO bootstrap_receipts (
                    receipt_id, bootstrap_id, compilation_id, outcome, target_root,
                    receipt_json, recorded_at_utc, actor_id, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    receipt.bootstrap_id,
                    receipt.compilation_id,
                    receipt.outcome.value,
                    receipt.target_root,
                    _json(document),
                    receipt.recorded_at_utc.isoformat(),
                    receipt.actor_id,
                    receipt.correlation_id,
                ),
            )
        return {"receipt_id": receipt_id, "changed": True}

    def list_bootstrap_receipts(self, compilation_id: str) -> tuple[BootstrapReceipt, ...]:
        rows = self.connection.execute(
            """
            SELECT receipt_json FROM bootstrap_receipts
            WHERE compilation_id = ? ORDER BY recorded_at_utc, receipt_id
            """,
            (compilation_id,),
        ).fetchall()
        return tuple(BootstrapReceipt.model_validate_json(row["receipt_json"]) for row in rows)

    def snapshot(self, project_id: str) -> dict[str, Any]:
        project_state = self.get_project_state(project_id)
        tasks = self.list_task_states(project_id)
        requirement_count = self.connection.execute("SELECT COUNT(*) FROM requirements").fetchone()[
            0
        ]
        link_count = self.connection.execute("SELECT COUNT(*) FROM traceability_links").fetchone()[
            0
        ]
        task_counts = dict(sorted(Counter(item.state.value for item in tasks).items()))
        intake_compilation_count = self.connection.execute(
            "SELECT COUNT(*) FROM intake_compilations"
        ).fetchone()[0]
        bootstrap_receipt_count = self.connection.execute(
            "SELECT COUNT(*) FROM bootstrap_receipts"
        ).fetchone()[0]
        return {
            "schema_version": "1.0.0",
            "project_id": project_id,
            "intake_compilation_count": intake_compilation_count,
            "bootstrap_receipt_count": bootstrap_receipt_count,
            "project_state": None
            if project_state is None
            else project_state.model_dump(mode="json"),
            "task_count": len(tasks),
            "task_counts": task_counts,
            "requirement_count": requirement_count,
            "traceability_link_count": link_count,
            "migration_status": self.migration_status(),
        }


def links_from_requirement(
    requirement: RequirementRecord,
    *,
    authority: TraceabilityAuthority = TraceabilityAuthority.AUTHORITATIVE_CATALOG,
) -> tuple[TraceabilityLink, ...]:
    result: list[TraceabilityLink] = []
    document = requirement.as_registry_row()
    for link_type, field in _LINK_FIELDS.items():
        raw_targets = document.get(field, [])
        targets = raw_targets if isinstance(raw_targets, (list, tuple)) else []
        for ordinal, target in enumerate(targets):
            result.append(
                TraceabilityLink.create(
                    requirement_id=requirement.requirement_id,
                    link_type=link_type,
                    target=str(target),
                    ordinal=ordinal,
                    authority=authority,
                )
            )
    return tuple(result)


def _link_from_row(row: sqlite3.Row) -> TraceabilityLink:
    return TraceabilityLink(
        link_id=row["link_id"],
        requirement_id=row["requirement_id"],
        link_type=row["link_type"],
        target=row["target"],
        ordinal=row["ordinal"],
        authority=row["authority"],
        metadata=json.loads(row["metadata_json"]),
    )


def catalog_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
