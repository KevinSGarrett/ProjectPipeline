from __future__ import annotations

from pathlib import Path

from project_pipeline.domain.github import (
    GitHubOperation,
    GitOperationState,
    GitOperationType,
    OwnershipKind,
)
from project_pipeline.github_steward.ownership import OwnershipRegistry
from project_pipeline.github_steward.persistence import GitHubStewardStore
from project_pipeline.persistence.migrations import load_migration_catalog


def test_migration_catalog_includes_repository_stewardship():
    catalog = load_migration_catalog(Path.cwd())
    by_id = {item.migration_id: item for item in catalog.migrations}
    assert by_id["PPDB-0005"].name == "repository_github_stewardship"
    assert any(item.migration_id == "PPDB-0005" for item in catalog.migrations)


def test_store_persists_ownership_and_operations(tmp_path):
    db = tmp_path / "state.db"
    with GitHubStewardStore(db, Path.cwd()) as store:
        claim = OwnershipRegistry().acquire(
            repository_slug="owner/repo",
            resource_kind=OwnershipKind.FILE,
            resource="src/a.py",
            owner_task_id="PP-TASK-1",
            workspace_id="ws-1",
        )
        store.save_ownership(claim)
        assert store.active_ownership("owner/repo") == (claim,)
        op = GitHubOperation.create(
            operation_type=GitOperationType.DELETE_BRANCH,
            repository_slug="owner/repo",
            target="feature/x",
            idempotency_key="delete-branch-0001",
            actor_id="actor:test",
            correlation_id="corr:test",
        )
        store.save_operation(op)
        loaded = store.get_operation(op.operation_id)
        assert loaded == op
        assert store.status("owner/repo")["operation_counts"] == {"PLANNED": 1}


def test_unknown_operation_appears_in_reconciliation_status(tmp_path):
    with GitHubStewardStore(tmp_path / "state.db", Path.cwd()) as store:
        op = GitHubOperation.create(
            operation_type=GitOperationType.MERGE_PULL_REQUEST,
            repository_slug="owner/repo",
            target="2",
            idempotency_key="merge-unknown-0001",
            actor_id="actor:test",
            correlation_id="corr:test",
            expected_head_sha="a" * 40,
        )
        store.save_operation(op.model_copy(update={"state": GitOperationState.UNKNOWN_OUTCOME}))
        status = store.status("owner/repo")
        assert status["reconciliation_required"]
        assert len(store.pending_operations("owner/repo")) == 1
