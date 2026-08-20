from datetime import UTC, datetime

from project_pipeline.context_engine import ContextBroker, ContextCompiler, ContextStore
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPolicy,
    ContextReceipt,
    ContextSourceKind,
    ContextTrust,
    DelegationEnvelope,
    ReceiptStatus,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


def build():
    now = datetime.now(UTC)
    e = DelegationEnvelope.create(objective="x", return_protocol="y", required_context_keys=("a",))
    c = ContextCandidate(
        context_key="a",
        kind=ContextSourceKind.OTHER,
        content="a",
        revision_id="1",
        observed_at_utc=now,
        trust=ContextTrust.AUTHORITATIVE,
    )
    p = ContextPolicy(policy_version="CTX-POLICY-1.0")
    pack = ContextCompiler().compile(
        e, ContextBroker().select(e, (c,), p), (c,), p, generated_at_utc=now
    )
    return e, pack


def test_context_store_roundtrip(tmp_path, project_root):
    e, pack = build()
    db = tmp_path / "state.db"
    with ContextStore(db, project_root) as s:
        s.save_delegation(e)
        s.save_pack(pack)
        assert s.get_pack(pack.pack_id) == pack
        rec = ContextReceipt.create(
            pack_id=pack.pack_id, worker_id="worker", status=ReceiptStatus.CONSUMED
        )
        s.save_receipt(rec)
        assert s.get_receipt(rec.receipt_id) == rec
        assert s.status() == {
            "schema_version": "1.0.0",
            "delegations": 1,
            "packs": 1,
            "receipts": 1,
        }


def test_context_pack_is_idempotent_and_collision_safe(tmp_path, project_root):
    e, pack = build()
    db = tmp_path / "state.db"
    with ContextStore(db, project_root) as s:
        s.save_delegation(e)
        s.save_pack(pack)
        s.save_pack(pack)
        assert s.status()["packs"] == 1


def test_migration_0009_applies_and_rolls_back(tmp_path, project_root):
    import sqlite3

    db = sqlite3.connect(tmp_path / "m.db")
    r = SQLiteMigrationRunner(db, project_root)
    status = r.apply_all()
    assert "PPDB-0009" in status.applied
    assert status.latest_applied == "PPDB-0025"

    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0024"
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0023"
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0022"
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0021"
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0020"
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0019"

    # Pass 25 audit immutability rolls back first without damaging lifecycle state.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0018"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "lifecycle_portfolio_projects" in names

    # Pass 22 lifecycle state rolls back next without damaging Pass 21 interaction state.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0017"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert (
        "lifecycle_portfolio_projects" not in names and "command_center_director_messages" in names
    )

    # Pass 21 interaction/delivery state rolls back next without damaging Command Center.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0016"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "command_center_events" in names and "command_center_director_messages" not in names

    # Command Center rolls back next without damaging Resilience, Security, Context, or Verification.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0015"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_packs" in names
    assert "verification_runs" in names
    assert "resilience_machines" in names
    assert "command_center_events" not in names

    # Resilience then rolls back without damaging Security, Context, or Verification.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0014"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_packs" in names
    assert "verification_runs" in names
    assert "resilience_machines" not in names

    # Security then rolls back without damaging Context or Verification.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0013"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_packs" in names
    assert "verification_runs" in names

    # Verification can roll back without damaging Context.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0012"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_packs" in names
    assert "orchestration_workflows" in names
    assert "budget_limits" in names
    assert "assurance_gate_evaluations" in names
    assert "verification_runs" not in names

    # Assurance can roll back without damaging Context or Budget.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0011"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_packs" in names
    assert "orchestration_workflows" in names
    assert "budget_limits" in names
    assert "assurance_gate_evaluations" not in names

    # Budget can roll back without damaging Context or Orchestration.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0010"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_packs" in names
    assert "orchestration_workflows" in names
    assert "budget_limits" not in names

    # Orchestration can roll back without damaging Context.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0009"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_packs" in names
    assert "orchestration_workflows" not in names

    # Finally rolling back PPDB-0009 removes only Context state.
    status = r.rollback_last()
    assert status.latest_applied == "PPDB-0008"
    names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_packs" not in names
