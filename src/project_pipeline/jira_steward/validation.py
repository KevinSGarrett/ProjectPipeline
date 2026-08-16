from __future__ import annotations

import sqlite3
from pathlib import Path

from project_pipeline.domain.jira import JiraLifecycleState
from project_pipeline.jira_steward.mock import MockJiraAdapter
from project_pipeline.jira_steward.persistence import JiraSyncStore
from project_pipeline.jira_steward.ports import JiraRemotePort
from project_pipeline.jira_steward.reconciliation import load_jira_reconciliation_policy
from project_pipeline.jira_steward.repository import JiraMirrorRepository

_REQUIRED_PATHS = (
    "config/jira/status_mapping.json",
    "config/jira/sync_policy.json",
    "database/migrations/sqlite/PPDB-0004_jira_steward_sync.up.sql",
    "database/migrations/sqlite/PPDB-0004_jira_steward_sync.down.sql",
    "database/migrations/postgresql/PPDB-0004_jira_steward_sync.up.sql",
    "database/migrations/postgresql/PPDB-0004_jira_steward_sync.down.sql",
    "src/project_pipeline/domain/jira.py",
    "src/project_pipeline/jira_steward/adapter.py",
    "src/project_pipeline/jira_steward/comments.py",
    "src/project_pipeline/jira_steward/mock.py",
    "src/project_pipeline/jira_steward/persistence.py",
    "src/project_pipeline/jira_steward/ports.py",
    "src/project_pipeline/jira_steward/reconciliation.py",
    "src/project_pipeline/jira_steward/repository.py",
    "src/project_pipeline/jira_steward/service.py",
)


def validate_jira_steward_foundation(root: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    for relative in _REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"Jira Steward foundation file is missing: {relative}")
    if errors:
        return errors
    try:
        policy = load_jira_reconciliation_policy(root)
    except Exception as error:
        errors.append(f"Jira reconciliation policy is invalid: {error}")
        return errors
    required_states = {
        JiraLifecycleState.BACKLOG,
        JiraLifecycleState.READY,
        JiraLifecycleState.IN_PROGRESS,
        JiraLifecycleState.REVIEW,
        JiraLifecycleState.VALIDATION,
        JiraLifecycleState.MERGE_READY,
        JiraLifecycleState.BLOCKED,
        JiraLifecycleState.DONE,
        JiraLifecycleState.CANCELLED,
        JiraLifecycleState.DEFERRED,
    }
    missing_targets = required_states - set(policy.preferred_remote_status)
    if missing_targets:
        errors.append(
            "Jira preferred remote status mapping is incomplete: "
            + ", ".join(sorted(item.value for item in missing_targets))
        )
    report = JiraMirrorRepository(root).validate()
    errors.extend(report.errors)
    adapter = MockJiraAdapter(project_key="PP")
    if not isinstance(adapter, JiraRemotePort):
        errors.append("Mock Jira adapter does not satisfy JiraRemotePort")
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        with JiraSyncStore(connection, root) as store:
            status = store.initialize()
            if "PPDB-0004" not in status["applied"]:
                errors.append("Jira synchronization migration PPDB-0004 is not applied")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for table in (
                "jira_remote_snapshots",
                "jira_reconciliation_plans",
                "jira_sync_operations",
                "jira_remote_mappings",
                "jira_sync_receipts",
            ):
                if table not in tables:
                    errors.append(f"Jira synchronization table is missing after migration: {table}")
    finally:
        connection.close()
    return sorted(set(errors))
