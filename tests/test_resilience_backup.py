import pytest

from project_pipeline.resilience.backup import BackupPlanner, load_recovery_objectives


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
