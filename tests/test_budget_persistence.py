from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.budget.persistence import BudgetStore
from project_pipeline.budget.service import BudgetGovernor
from project_pipeline.domain.budget import (
    BudgetAdmissionRequest,
    BudgetLimit,
    BudgetScopeType,
    CostClass,
    CostEvidenceState,
    ReserveReason,
    SpendLeaseState,
    budget_identifier,
)

NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)


def limit(cap=1_000_000, reserve=200_000):
    return BudgetLimit(
        limit_id=budget_identifier("LIMIT", "GLOBAL:*", "2026-08"),
        scope_type=BudgetScopeType.GLOBAL,
        scope_id="*",
        cycle_id="2026-08",
        hard_cap_microunits=cap,
        soft_cap_microunits=cap - reserve,
        protected_reserve_microunits=reserve,
    )


def request(task, cost, **kwargs):
    data = dict(
        project_id="PROJECT-PIPELINE",
        task_id=task,
        task_class="code",
        scope_keys=("GLOBAL:*",),
        estimated_p50_microunits=cost // 2,
        estimated_p90_microunits=cost,
    )
    data.update(kwargs)
    return BudgetAdmissionRequest(**data)


def test_atomic_reservations_prevent_concurrent_overspend(tmp_path: Path):
    db = tmp_path / "budget.db"
    with BudgetStore(db, Path.cwd()) as store:
        gov = BudgetGovernor(store)
        gov.configure_limit(limit())
        req1 = request("PP-TASK-1", 500_000)
        dec1 = gov.admit(req1, cycle_id="2026-08", now=NOW)
        assert dec1.admitted
        gov.reserve(req1, dec1, cycle_id="2026-08", idempotency_key="r1", now=NOW)
        req2 = request("PP-TASK-2", 400_000)
        dec2 = gov.admit(req2, cycle_id="2026-08", now=NOW)
        assert not dec2.admitted
        assert "insufficient_budget_for_p90" in dec2.reasons


def test_reservation_is_idempotent(tmp_path: Path):
    with BudgetStore(tmp_path / "b.db", Path.cwd()) as store:
        gov = BudgetGovernor(store)
        gov.configure_limit(limit())
        req = request("PP-TASK-1", 100_000)
        dec = gov.admit(req, cycle_id="2026-08", now=NOW)
        a = gov.reserve(req, dec, cycle_id="2026-08", idempotency_key="same", now=NOW)
        b = gov.reserve(req, dec, cycle_id="2026-08", idempotency_key="same", now=NOW)
        assert a == b
        assert len(store.list_active_leases(now=NOW)) == 1


def test_unknown_outcome_holds_reservation_until_reconciled(tmp_path: Path):
    with BudgetStore(tmp_path / "b.db", Path.cwd()) as store:
        gov = BudgetGovernor(store)
        gov.configure_limit(limit())
        req = request("PP-TASK-1", 100_000)
        dec = gov.admit(req, cycle_id="2026-08", now=NOW)
        lease = gov.reserve(req, dec, cycle_id="2026-08", idempotency_key="unknown", now=NOW)
        held = gov.mark_unknown_outcome(lease.lease_id, now=NOW)
        assert held.state is SpendLeaseState.UNKNOWN_OUTCOME
        with pytest.raises(ValueError):
            store.release_lease(held.lease_id, now=NOW)
        # Expiry does not release an ambiguous remote effect.
        assert store.expire_stale_leases(now=NOW + timedelta(days=2)) == ()
        released = gov.reconcile_unknown(
            held.lease_id, remote_effect_occurred=False, now=NOW + timedelta(days=2)
        )
        assert released.state is SpendLeaseState.RELEASED


def test_settlement_moves_reservation_to_immutable_ledger(tmp_path: Path):
    with BudgetStore(tmp_path / "b.db", Path.cwd()) as store:
        gov = BudgetGovernor(store)
        gov.configure_limit(limit())
        req = request("PP-TASK-1", 100_000)
        dec = gov.admit(req, cycle_id="2026-08", now=NOW)
        lease = gov.reserve(req, dec, cycle_id="2026-08", idempotency_key="settle", now=NOW)
        entry = gov.make_usage_entry(
            idempotency_key="usage-1",
            project_id="PROJECT-PIPELINE",
            task_id="PP-TASK-1",
            scope_keys=("GLOBAL:*",),
            cost_class=CostClass.PROVIDER,
            evidence_state=CostEvidenceState.RECONCILED,
            cash_microunits=75_000,
            observed_at_utc=NOW,
        )
        settled = gov.settle(lease.lease_id, entry, now=NOW)
        assert settled.state is SpendLeaseState.SETTLED
        assert store.list_ledger(project_id="PROJECT-PIPELINE") == (entry,)
        snap = store.snapshot(limit(), now=NOW)
        assert snap.spent_microunits == 75_000
        assert snap.committed_microunits == 0


def test_overspend_is_recorded_not_erased(tmp_path: Path):
    with BudgetStore(tmp_path / "b.db", Path.cwd()) as store:
        gov = BudgetGovernor(store)
        gov.configure_limit(limit())
        req = request("PP-TASK-1", 100_000)
        dec = gov.admit(req, cycle_id="2026-08", now=NOW)
        lease = gov.reserve(req, dec, cycle_id="2026-08", idempotency_key="over", now=NOW)
        entry = gov.make_usage_entry(
            idempotency_key="over-usage",
            project_id="PROJECT-PIPELINE",
            task_id="PP-TASK-1",
            scope_keys=("GLOBAL:*",),
            cost_class=CostClass.PROVIDER,
            evidence_state=CostEvidenceState.PROVIDER_REPORTED,
            cash_microunits=120_000,
            observed_at_utc=NOW,
        )
        result = gov.settle(lease.lease_id, entry, now=NOW)
        assert result.state is SpendLeaseState.OVERSPENT
        assert store.list_ledger()[0].cash_microunits == 120_000


def test_protected_reserve_requires_critical_justification(tmp_path: Path):
    with BudgetStore(tmp_path / "b.db", Path.cwd()) as store:
        gov = BudgetGovernor(store)
        gov.configure_limit(limit())
        # Fill most normal budget.
        r1 = request("PP-TASK-1", 750_000)
        d1 = gov.admit(r1, cycle_id="2026-08", now=NOW)
        l1 = gov.reserve(r1, d1, cycle_id="2026-08", idempotency_key="fill", now=NOW)
        e1 = gov.make_usage_entry(
            idempotency_key="fill-u",
            project_id="PROJECT-PIPELINE",
            task_id="PP-TASK-1",
            scope_keys=("GLOBAL:*",),
            cost_class=CostClass.PROVIDER,
            evidence_state=CostEvidenceState.RECONCILED,
            cash_microunits=750_000,
            observed_at_utc=NOW,
        )
        gov.settle(l1.lease_id, e1, now=NOW)
        ordinary = request("PP-TASK-2", 100_000)
        assert not gov.admit(ordinary, cycle_id="2026-08", now=NOW).admitted
        critical = request(
            "PP-TASK-3",
            100_000,
            priority="P0",
            critical_path=True,
            reserve_reason=ReserveReason.CRITICAL_PATH,
        )
        decision = gov.admit(critical, cycle_id="2026-08", now=NOW)
        assert decision.admitted and decision.reserve_authorized
