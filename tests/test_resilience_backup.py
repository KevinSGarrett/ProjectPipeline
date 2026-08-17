import pytest

from project_pipeline.resilience.backup import (
    BackupPlanner,
    build_integrity_manifest,
    load_recovery_objectives,
)


def test_canonical_state_uses_pgbackrest(project_root):
    p = BackupPlanner(load_recovery_objectives(project_root))
    x = p.plan_backup(domain="canonical_state", source="postgres", repository="repo")
    assert x["tool"] == "PGBACKREST" and not x["live_execution_performed"]


def test_general_backup_uses_restic(project_root):
    p = BackupPlanner(load_recovery_objectives(project_root))
    x = p.plan_backup(domain="artifacts", source="artifacts", repository="repo")
    assert x["tool"] == "RESTIC"


def test_restore_requires_isolated_target_and_separate_verification(project_root):
    p = BackupPlanner(load_recovery_objectives(project_root))
    x = p.plan_restore(
        domain="canonical_state", repository="repo", isolated_target=".local/recovery/db"
    )
    assert x["verification_required"] and x["backup_status_is_not_restore_status"]
    with pytest.raises(ValueError):
        p.plan_restore(domain="canonical_state", repository="repo", isolated_target="/")
    with pytest.raises(ValueError):
        p.plan_restore(domain="canonical_state", repository="repo", isolated_target="C:/")


def test_restore_verification_plan_covers_failure_matrix(project_root):
    p = BackupPlanner(load_recovery_objectives(project_root))
    plan = p.plan_restore_verification(
        domain="canonical_state",
        backup_id="BACKUP-TEST-001",
        isolated_target=".local/recovery/verify",
    )
    assert plan["idempotent_retry_required"]
    assert plan["restore_result_distinct_from_backup_result"]
    assert "unknown_outcome" in plan["failure_cases"]
    assert "locked_file" in plan["failure_cases"]


def test_integrity_manifest_requires_unique_valid_entries():
    manifest = build_integrity_manifest(
        [
            {"path": "state.db", "sha256": "a" * 64, "size_bytes": 42},
            {"path": "events.jsonl", "sha256": "b" * 64, "size_bytes": 99},
        ]
    )
    assert manifest["entry_count"] == 2
    assert len(manifest["aggregate_sha256"]) == 64
    with pytest.raises(ValueError):
        build_integrity_manifest([])
    with pytest.raises(ValueError):
        build_integrity_manifest(
            [
                {"path": "state.db", "sha256": "a" * 64, "size_bytes": 42},
                {"path": "state.db", "sha256": "b" * 64, "size_bytes": 99},
            ]
        )
