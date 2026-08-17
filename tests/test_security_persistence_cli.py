import subprocess
import sys
from datetime import UTC, datetime, timedelta

from project_pipeline.domain.security import (
    AuthorityCapability,
    CapabilityGrant,
    IdentityKind,
    RootOfTrust,
    SecretBackendKind,
    SecretCapabilityReference,
    SecurityIdentity,
    security_identifier,
)
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
        assert store.get_identity(value.identity_id) == value
        assert store.list_identities(limit=10) == (value,)
        ids = {r[0] for r in store.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0014" in ids


def test_security_store_pagination_and_idempotent_replay(project_root, tmp_path):
    db = tmp_path / "s.db"
    first = SecurityIdentity(
        identity_id=security_identifier("IDENT", "first"),
        kind=IdentityKind.AGENT,
        display_name="First",
        principal="agent:first",
    )
    second = SecurityIdentity(
        identity_id=security_identifier("IDENT", "second"),
        kind=IdentityKind.AGENT,
        display_name="Second",
        principal="agent:second",
    )
    with SecurityStore(db, project_root) as store:
        store.save_identity(first)
        store.save_identity(first)
        store.save_identity(second)
        assert store.status()["security_identities"] == 2
        assert store.list_identities(limit=0)  # clamps to bounded minimum
        assert store.list_identities(limit=-5)  # clamps to bounded minimum
        assert len(store.list_identities(limit=9999)) == 2  # clamps to bounded maximum
        page = store.list_identities(limit=1, offset=1)
        assert len(page) == 1
        assert page[0].identity_id in {first.identity_id, second.identity_id}
        assert store.get_identity("IDENT-NOT-REAL-0000000000") is None


def test_security_store_additional_entity_roundtrip(project_root, tmp_path):
    db = tmp_path / "s.db"
    now = datetime.now(UTC)
    identity = SecurityIdentity(
        identity_id=security_identifier("IDENT", "store-entity"),
        kind=IdentityKind.AGENT,
        display_name="Store Entity",
        principal="agent:store-entity",
    )
    grant = CapabilityGrant(
        grant_id=security_identifier("GRANT", "store-entity"),
        identity_id=identity.identity_id,
        capability=AuthorityCapability.MUTATE,
        project_id="PROJECT-PIPELINE",
        target_prefix="src/project_pipeline/security",
        environment="local",
        operation_class="security-write",
        issued_by=identity.identity_id,
        issued_at_utc=now,
        expires_at_utc=now + timedelta(minutes=10),
    )
    secret_ref = SecretCapabilityReference(
        secret_ref_id=security_identifier("SREF", "store-entity"),
        logical_name="JIRA_TOKEN",
        backend=SecretBackendKind.ENVIRONMENT,
        reference="env://JIRA_API_TOKEN",
        allowed_operations=("jira_snapshot",),
        allowed_target_prefixes=("jira/",),
    )
    root = RootOfTrust(
        root_id=security_identifier("ROOTTRUST", "store-entity"),
        bootstrap_identity_id=identity.identity_id,
        trusted_policy_paths=("config/security_policy.json",),
        trusted_key_references=("env://SECURITY_SIGNING_KEY",),
        recovery_procedure="runbook-recovery",
        rotation_procedure="runbook-rotation",
        revocation_procedure="runbook-revocation",
    )
    with SecurityStore(db, project_root) as store:
        store.save_identity(identity)
        store.save_grant(grant)
        store.save_secret_reference(secret_ref)
        store.save_root_of_trust(root)
        assert store.get_grant(grant.grant_id) == grant
        assert store.get_secret_reference(secret_ref.secret_ref_id) == secret_ref
        assert store.get_root_of_trust(root.root_id) == root
        assert store.list_grants(limit=10, offset=0) == (grant,)
        assert store.list_secret_references(limit=10, offset=0) == (secret_ref,)
        assert store.list_root_of_trust(limit=10, offset=0) == (root,)


def test_ppdb_0014_rollback_preserves_0013(project_root, tmp_path):
    db = tmp_path / "s.db"
    with SecurityStore(db, project_root) as store:
        runner = __import__(
            "project_pipeline.persistence.migrations", fromlist=["SQLiteMigrationRunner"]
        ).SQLiteMigrationRunner(store.db, project_root)
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
    listed = run(
        project_root,
        "identities",
        "--database",
        str(tmp_path / "x.db"),
        "--limit",
        "1",
    )
    assert listed.returncode == 0
    assert value.identity_id in listed.stdout

    filtered = run(
        project_root,
        "identities",
        "--database",
        str(tmp_path / "x.db"),
        "--identity-id",
        value.identity_id,
    )
    assert filtered.returncode == 0
    assert value.identity_id in filtered.stdout


def test_security_cli_query_actions_are_read_only(project_root, tmp_path):
    db = tmp_path / "q.db"
    now = datetime.now(UTC)
    identity = SecurityIdentity(
        identity_id=security_identifier("IDENT", "cli-query"),
        kind=IdentityKind.AGENT,
        display_name="CLI Query",
        principal="agent:cli-query",
    )
    grant = CapabilityGrant(
        grant_id=security_identifier("GRANT", "cli-query"),
        identity_id=identity.identity_id,
        capability=AuthorityCapability.MUTATE,
        project_id="PROJECT-PIPELINE",
        target_prefix="src/project_pipeline/security",
        environment="local",
        operation_class="security-write",
        issued_by=identity.identity_id,
        issued_at_utc=now,
        expires_at_utc=now + timedelta(minutes=10),
    )
    secret_ref = SecretCapabilityReference(
        secret_ref_id=security_identifier("SREF", "cli-query"),
        logical_name="JIRA_TOKEN",
        backend=SecretBackendKind.ENVIRONMENT,
        reference="env://JIRA_API_TOKEN",
        allowed_operations=("jira_snapshot",),
        allowed_target_prefixes=("jira/",),
    )
    with SecurityStore(db, project_root) as store:
        store.save_identity(identity)
        store.save_grant(grant)
        store.save_secret_reference(secret_ref)

    for action, needle in (
        ("grants", grant.grant_id),
        ("secret-references", secret_ref.secret_ref_id),
        ("secret-leases", "secret_leases"),
    ):
        result = run(project_root, action, "--database", str(db), "--limit", "10", "--offset", "0")
        assert result.returncode == 0
        assert needle in result.stdout


def test_security_cli_simulations(project_root):
    for scenario in ("least-privilege", "egress-secret-block", "independent-approval"):
        r = run(project_root, "simulate", "--scenario", scenario)
        assert r.returncode == 0
