from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.domain import (
    ProjectLifecycleState,
    ProjectManifest,
    ProjectOrigin,
    ProjectRepository,
    RepositoryRole,
    TaskStateRecord,
    task_state_from_jira,
)
from project_pipeline.io import read_json, write_json
from project_pipeline.jira import load_issues
from project_pipeline.persistence import SQLiteStateStore

PROJECT_MANIFEST_PATH = Path("config/project_manifest.json")


def build_project_manifest(root: Path) -> ProjectManifest:
    root = root.resolve()
    project = read_json(root / "config" / "project.json")
    existing_path = root / PROJECT_MANIFEST_PATH
    existing = (
        ProjectManifest.model_validate(read_json(existing_path)) if existing_path.exists() else None
    )
    now = datetime.now(UTC)
    return ProjectManifest(
        project_id=project["project_id"],
        project_name=project["name"],
        root_path=".",
        origin=ProjectOrigin.ADOPTED,
        profile="local",
        revision=1 if existing is None else existing.revision,
        repositories=(
            ProjectRepository(
                repository_id="project-pipeline",
                root_path=".",
                role=RepositoryRole.PRIMARY,
                canonical_url=project.get("repository"),
            ),
        ),
        source_registry_path="provenance/source_registry.json",
        requirement_registry_path="plans/_traceability/requirements.jsonl",
        plan_catalog_path="plans/PLAN_CATALOG.json",
        jira_index_path="jira/indexes/issues.jsonl",
        evidence_ledger_path="evidence/EVIDENCE_LEDGER.jsonl",
        created_at_utc=now if existing is None else existing.created_at_utc,
        updated_at_utc=now,
    )


def write_project_domain_manifest(root: Path) -> ProjectManifest:
    manifest = build_project_manifest(root)
    path = root / PROJECT_MANIFEST_PATH
    existing = ProjectManifest.model_validate(read_json(path)) if path.exists() else None
    if existing is not None:
        old = existing.model_copy(update={"updated_at_utc": manifest.updated_at_utc})
        if old.semantic_fingerprint() != manifest.semantic_fingerprint():
            manifest = manifest.model_copy(update={"revision": existing.revision + 1})
        else:
            manifest = manifest.model_copy(
                update={
                    "revision": existing.revision,
                    "created_at_utc": existing.created_at_utc,
                    "updated_at_utc": existing.updated_at_utc,
                }
            )
    write_json(path, manifest.model_dump(mode="json"))
    return manifest


def validate_project_domain_manifest(root: Path) -> list[str]:
    errors: list[str] = []
    path = root / PROJECT_MANIFEST_PATH
    if not path.exists():
        return [f"{PROJECT_MANIFEST_PATH.as_posix()} is missing"]
    try:
        manifest = ProjectManifest.model_validate(read_json(path))
    except Exception as error:
        return [f"project domain manifest is invalid: {error}"]
    expected_paths = (
        manifest.source_registry_path,
        manifest.requirement_registry_path,
        manifest.plan_catalog_path,
        manifest.jira_index_path,
        manifest.evidence_ledger_path,
    )
    for relative in expected_paths:
        if not (root / relative).exists():
            errors.append(f"project domain manifest references a missing path: {relative}")
    primary = manifest.primary_repository()
    if primary.root_path != ".":
        errors.append("primary project repository must remain relative to the project root")
    project = read_json(root / "config" / "project.json")
    if manifest.project_id != project.get("project_id"):
        errors.append("project domain manifest identity differs from config/project.json")
    return errors


def task_records_from_jira(root: Path, project_id: str) -> tuple[TaskStateRecord, ...]:
    result: list[TaskStateRecord] = []
    for issue in load_issues(root):
        state = task_state_from_jira(issue["state"])
        dependencies = tuple(
            sorted(
                {
                    *issue.get("dependencies", []),
                    *(
                        relation["target"]
                        for relation in issue.get("relationships", [])
                        if relation.get("type") in {"DEPENDS_ON", "IS_BLOCKED_BY"}
                    ),
                }
            )
        )
        blockers = tuple(sorted(set(issue.get("blockers", []))))
        blocked_reason = None
        if state.value == "BLOCKED":
            blocked_reason = (
                "Imported work item is blocked by: " + ", ".join(blockers)
                if blockers
                else "Imported work item is in a blocked state."
            )
        result.append(
            TaskStateRecord(
                task_id=issue["local_id"],
                project_id=project_id,
                state=state,
                priority="P0" if issue.get("risk_classification") == "CRITICAL" else "P1",
                dependency_ids=dependencies,
                blocker_ids=blockers,
                blocked_reason=blocked_reason,
            )
        )
    return tuple(result)


class CoreStateService:
    def __init__(self, store: SQLiteStateStore, root: Path) -> None:
        self.store = store
        self.root = root.resolve()

    def initialize_from_repository(
        self,
        *,
        actor_id: str = "actor:local-bootstrap",
        correlation_id: str = "corr:core-state-bootstrap",
    ) -> dict[str, Any]:
        self.store.initialize()
        manifest = write_project_domain_manifest(self.root)
        self.store.put_project_manifest(manifest)
        project_state = self.store.get_project_state(manifest.project_id)
        if project_state is None:
            raise RuntimeError("project state was not initialized")
        if project_state.state is ProjectLifecycleState.REGISTERED:
            project_state = self.store.transition_project(
                project_id=manifest.project_id,
                next_state=ProjectLifecycleState.COMPILING,
                expected_version=project_state.version,
                reason="Import the authoritative project, requirement, plan, and work registries.",
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
        tasks = task_records_from_jira(self.root, manifest.project_id)
        self.store.put_task_states(tasks)
        self.refresh_task_counts(manifest.project_id)
        project_state = self.store.get_project_state(manifest.project_id)
        if project_state is None:
            raise RuntimeError("project state disappeared during initialization")
        if project_state.state is ProjectLifecycleState.COMPILING:
            project_state = self.store.transition_project(
                project_id=manifest.project_id,
                next_state=ProjectLifecycleState.READY,
                expected_version=project_state.version,
                reason="Core repository state compiled into the deterministic local persistence profile.",
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
        self.refresh_task_counts(manifest.project_id)
        return self.store.snapshot(manifest.project_id)

    def refresh_task_counts(self, project_id: str) -> dict[str, int]:
        states = self.store.list_task_states(project_id)
        counts = dict(sorted(Counter(item.state.value for item in states).items()))
        with self.store.transaction() as connection:
            connection.execute(
                """
                UPDATE project_states SET task_counts_json = ?, updated_at_utc = ?
                WHERE project_id = ?
                """,
                (
                    json.dumps(counts, sort_keys=True, separators=(",", ":")),
                    datetime.now(UTC).isoformat(),
                    project_id,
                ),
            )
        return counts
