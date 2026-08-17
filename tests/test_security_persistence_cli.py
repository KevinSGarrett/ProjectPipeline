import subprocess
import sys

from project_pipeline.domain.security import IdentityKind, SecurityIdentity, security_identifier
from project_pipeline.security.persistence import SecurityStore


def test_ppdb_0014_and_store_roundtrip(project_root, tmp_path):
    db = tmp_path / "s.db"
    value = SecurityIdentity(
        identity_id=security_identifier("IDENT", "persist"),
        kind=IdentityKind.AGENT,
        display_name="Persist",
        principal="agent:persist",
    )
    with SecurityStore(db, project_root) as store:
        store.save_identity(value)
        assert store.status()["security_identities"] == 1
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0014" in ids


def test_ppdb_0014_rollback_preserves_0013(project_root, tmp_path):
    db = tmp_path / "s.db"
    with SecurityStore(db, project_root) as store:
        runner = __import__(
            "project_pipeline.persistence.migrations", fromlist=["SQLiteMigrationRunner"]
        ).SQLiteMigrationRunner(store.db, project_root)
        runner.rollback_last()  # PPDB-0021 unattended qualification
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0020" in ids and "PPDB-0021" not in ids
        runner.rollback_last()  # PPDB-0020 autonomy runtime supervisor
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0019" in ids and "PPDB-0020" not in ids
        runner.rollback_last()  # PPDB-0019 audit immutability triggers
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0018" in ids and "PPDB-0019" not in ids
        runner.rollback_last()  # PPDB-0018 platform lifecycle state
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0017" in ids and "PPDB-0018" not in ids
        runner.rollback_last()  # PPDB-0017 Director/incident/notification state
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0016" in ids and "PPDB-0017" not in ids
        runner.rollback_last()  # PPDB-0016 command center
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0015" in ids and "PPDB-0016" not in ids
        runner.rollback_last()  # PPDB-0015 resilience
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0014" in ids and "PPDB-0015" not in ids
        runner.rollback_last()  # PPDB-0014 security
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0014" not in ids and "PPDB-0013" in ids


def run(root, *args):
    return subprocess.run(
        [sys.executable, "-m", "project_pipeline", "security", *args, "--root", str(root)],
        cwd=root,
        text=True,
        capture_output=True,
        env={**__import__("os").environ, "PYTHONPATH": str(root / "src")},
    )


def test_security_cli_tools_and_supply_chain(project_root):
    a = run(project_root, "tools")
    assert a.returncode == 0 and "security_tools" in a.stdout
    b = run(project_root, "supply-chain")
    assert b.returncode == 0 and "supply_chain_gate" in b.stdout


def test_security_cli_record_identity_requires_approval(project_root, tmp_path):
    value = SecurityIdentity(
        identity_id=security_identifier("IDENT", "cli"),
        kind=IdentityKind.AGENT,
        display_name="CLI",
        principal="agent:cli",
    )
    f = tmp_path / "i.json"
    f.write_text(value.model_dump_json())
    denied = run(
        project_root, "record-identity", "--input", str(f), "--database", str(tmp_path / "x.db")
    )
    assert denied.returncode == 2 and "--apply --approve" in denied.stdout
    ok = run(
        project_root,
        "record-identity",
        "--input",
        str(f),
        "--database",
        str(tmp_path / "x.db"),
        "--apply",
        "--approve",
    )
    assert ok.returncode == 0 and value.identity_id in ok.stdout


def test_security_cli_simulations(project_root):
    for scenario in ("least-privilege", "egress-secret-block", "independent-approval"):
        r = run(project_root, "simulate", "--scenario", scenario)
        assert r.returncode == 0
