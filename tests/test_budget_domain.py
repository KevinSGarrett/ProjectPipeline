from datetime import UTC, datetime, timedelta

import pytest

from project_pipeline.domain.budget import (
    BudgetAdmissionRequest,
    BudgetLedgerEntry,
    BudgetLimit,
    BudgetScopeType,
    CostClass,
    CostEvidenceState,
    LedgerDirection,
    SpendLease,
    SpendLeaseState,
    budget_identifier,
)

NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)


def test_limit_identity_and_normal_cap():
    limit = BudgetLimit(
        limit_id=budget_identifier("LIMIT", "GLOBAL:*", "2026-08"),
        scope_type=BudgetScopeType.GLOBAL,
        scope_id="*",
        cycle_id="2026-08",
        hard_cap_microunits=300_000_000,
        protected_reserve_microunits=80_000_000,
    )
    assert limit.normal_cap_microunits == 220_000_000


def test_limit_rejects_reserve_above_cap():
    with pytest.raises(ValueError):
        BudgetLimit(
            limit_id=budget_identifier("LIMIT", "GLOBAL:*", "2026-08"),
            scope_type=BudgetScopeType.GLOBAL,
            scope_id="*",
            cycle_id="2026-08",
            hard_cap_microunits=10,
            protected_reserve_microunits=11,
        )


def test_ledger_identity_and_signed_credit():
    entry = BudgetLedgerEntry(
        entry_id=budget_identifier("ENTRY", "refund-1"),
        idempotency_key="refund-1",
        project_id="PROJECT-PIPELINE",
        cost_class=CostClass.PROVIDER,
        direction=LedgerDirection.CREDIT,
        cash_microunits=1000,
        scope_keys=("PROJECT:PROJECT-PIPELINE", "GLOBAL:*"),
        evidence_state=CostEvidenceState.RECONCILED,
        observed_at_utc=NOW,
        recorded_at_utc=NOW,
    )
    assert entry.signed_cash_microunits == -1000
    assert entry.scope_keys == ("GLOBAL:*", "PROJECT:PROJECT-PIPELINE")


def test_spend_lease_unknown_outcome_requires_reconciliation():
    with pytest.raises(ValueError):
        SpendLease(
            lease_id=budget_identifier("LEASE", "lease-1"),
            idempotency_key="lease-1",
            project_id="PROJECT-PIPELINE",
            task_id="PP-TASK-1",
            scope_keys=("GLOBAL:*",),
            maximum_microunits=100,
            reserved_microunits=100,
            state=SpendLeaseState.UNKNOWN_OUTCOME,
            created_at_utc=NOW,
            expires_at_utc=NOW + timedelta(hours=1),
            updated_at_utc=NOW,
        )


def test_admission_request_rejects_p90_below_p50():
    with pytest.raises(ValueError):
        BudgetAdmissionRequest(
            project_id="PROJECT-PIPELINE",
            task_id="PP-TASK-1",
            task_class="implementation",
            scope_keys=("GLOBAL:*",),
            estimated_p50_microunits=100,
            estimated_p90_microunits=99,
        )
