from datetime import UTC, datetime

from project_pipeline.domain.resilience import (
    MachineHealth,
    MachineRole,
    RecoveryObjective,
    resilience_identifier,
)
from project_pipeline.resilience.persistence import ResilienceStore


def test_ppdb_0015_and_store_roundtrip(project_root, tmp_path):
    db = tmp_path / "r.db"
    m = MachineHealth(
        machine_id="control-a",
        roles=(MachineRole.PRIMARY_CONTROL,),
        healthy=True,
        heartbeat_at_utc=datetime.now(UTC),
        fencing_token=1,
    )
    o = RecoveryObjective(
        objective_id=resilience_identifier("RPO", "state"),
        domain="state",
        rpo_seconds=300,
        rto_seconds=1800,
        backup_strategy="backup safely",
        destructive_restore_interval_days=30,
        rationale="required",
    )
    with ResilienceStore(db, project_root) as s:
        s.save_machine(m)
        s.save_objective(o)
        assert s.status()["resilience_machines"] == 1
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert {"PPDB-0015", "PPDB-0016", "PPDB-0017", "PPDB-0018"} <= ids


def test_ppdb_0015_rollback_preserves_0014(project_root, tmp_path):
    from project_pipeline.persistence.migrations import SQLiteMigrationRunner

    db = tmp_path / "r.db"
    with ResilienceStore(db, project_root) as s:
        runner = SQLiteMigrationRunner(s.db, project_root)
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0022" in ids and "PPDB-0023" not in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0021" in ids and "PPDB-0022" not in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0020" in ids and "PPDB-0021" not in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0019" in ids and "PPDB-0020" not in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0018" in ids and "PPDB-0019" not in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0017" in ids and "PPDB-0018" not in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0016" in ids and "PPDB-0017" not in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0015" in ids and "PPDB-0016" not in ids
