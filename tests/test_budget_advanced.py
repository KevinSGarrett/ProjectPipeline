from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_pipeline.budget.persistence import BudgetStore
from project_pipeline.budget.policy import rebalance_provider_soft_envelopes
from project_pipeline.budget.service import BudgetGovernor
from project_pipeline.domain.budget import (
    BudgetAdmissionRequest,
    BudgetLimit,
    BudgetScopeType,
    QuotaLimit,
    budget_identifier,
)

NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)


def _limit(cap: int = 1_000_000, reserve: int = 200_000) -> BudgetLimit:
    return BudgetLimit(
        limit_id=budget_identifier("LIMIT", "GLOBAL:*", "2026-08"),
        scope_type=BudgetScopeType.GLOBAL,
        scope_id="*",
        cycle_id="2026-08",
        hard_cap_microunits=cap,
        soft_cap_microunits=cap - reserve,
        protected_reserve_microunits=reserve,
    )


def _request(
    task_id: str, cost: int, quota: dict[str, int] | None = None
) -> BudgetAdmissionRequest:
    return BudgetAdmissionRequest(
        project_id="PROJECT-PIPELINE",
        task_id=task_id,
        task_class="implementation",
        scope_keys=("GLOBAL:*",),
        estimated_p50_microunits=cost // 2,
        estimated_p90_microunits=cost,
        quota_requirements=quota or {},
    )


def test_atomic_recheck_closes_preapproved_reservation_race(tmp_path: Path):
    with BudgetStore(tmp_path / "budget.db", Path.cwd()) as store:
        governor = BudgetGovernor(store)
        governor.configure_limit(_limit())
        first = _request("PP-TASK-RACE-1", 500_000)
        second = _request("PP-TASK-RACE-2", 400_000)
        first_decision = governor.admit(first, cycle_id="2026-08", now=NOW)
        second_decision = governor.admit(second, cycle_id="2026-08", now=NOW)
        assert first_decision.admitted and second_decision.admitted
        governor.reserve(
            first, first_decision, cycle_id="2026-08", idempotency_key="race-1", now=NOW
        )
        with pytest.raises(ValueError, match="atomic budget reservation"):
            governor.reserve(
                second, second_decision, cycle_id="2026-08", idempotency_key="race-2", now=NOW
            )


def test_atomic_quota_recheck_closes_preapproved_quota_race(tmp_path: Path):
    quota_id = budget_identifier("QUOTA", "PROJECT:PROJECT-PIPELINE", "provider:test", "requests")
    quota = QuotaLimit(
        quota_id=quota_id,
        scope_key="PROJECT:PROJECT-PIPELINE",
        provider_id="provider:test",
        quota_name="requests",
        capacity_units=100,
        protected_units=20,
        max_shadow_cost_microunits=100_000,
    )
    with BudgetStore(tmp_path / "budget.db", Path.cwd()) as store:
        governor = BudgetGovernor(store)
        governor.configure_limit(_limit())
        governor.configure_quota(quota)
        first = _request("PP-TASK-QUOTA-1", 10_000, {quota_id: 50})
        second = _request("PP-TASK-QUOTA-2", 10_000, {quota_id: 40})
        first_decision = governor.admit(first, cycle_id="2026-08", now=NOW)
        second_decision = governor.admit(second, cycle_id="2026-08", now=NOW)
        assert first_decision.admitted and second_decision.admitted
        governor.reserve(
            first, first_decision, cycle_id="2026-08", idempotency_key="quota-race-1", now=NOW
        )
        with pytest.raises(ValueError, match="atomic quota reservation"):
            governor.reserve(
                second, second_decision, cycle_id="2026-08", idempotency_key="quota-race-2", now=NOW
            )


def test_provider_soft_rebalance_never_changes_hard_caps():
    hard = {"anthropic": 400_000, "openai": 500_000, "local": 100_000}
    result = rebalance_provider_soft_envelopes(
        global_limit_microunits=700_000,
        provider_hard_caps=hard,
        demand_microunits={"anthropic": 100_000, "openai": 900_000, "local": 10_000},
    )
    assert sum(result.values()) == 700_000
    assert all(result[key] <= hard[key] for key in hard)
    assert result["openai"] > result["anthropic"]


def test_anomaly_detection_warns_then_blocks_and_persists(tmp_path: Path):
    with BudgetStore(tmp_path / "budget.db", Path.cwd()) as store:
        governor = BudgetGovernor(store)
        warn = governor.detect_anomaly(
            project_id="PROJECT-PIPELINE",
            expected_p90_microunits=100_000,
            observed_microunits=160_000,
            task_id="PP-TASK-A",
            now=NOW,
        )
        block = governor.detect_anomaly(
            project_id="PROJECT-PIPELINE",
            expected_p90_microunits=100_000,
            observed_microunits=260_000,
            task_id="PP-TASK-B",
            now=NOW,
        )
        assert warn.severity == "WARN" and not warn.block_new_paid_work
        assert block.severity == "BLOCK" and block.block_new_paid_work
        assert store.status("PROJECT-PIPELINE")["blocking_anomaly_count"] == 1


def test_budget_limit_change_reports_active_commitment_impact(tmp_path: Path):
    with BudgetStore(tmp_path / "budget.db", Path.cwd()) as store:
        governor = BudgetGovernor(store)
        old = _limit(1_000_000, 200_000)
        governor.configure_limit(old)
        request = _request("PP-TASK-IMPACT", 500_000)
        decision = governor.admit(request, cycle_id="2026-08", now=NOW)
        governor.reserve(request, decision, cycle_id="2026-08", idempotency_key="impact", now=NOW)
        new = old.model_copy(
            update={
                "hard_cap_microunits": 400_000,
                "soft_cap_microunits": 400_000,
                "protected_reserve_microunits": 0,
            }
        )
        impact = governor.analyze_limit_change(old, new, now=NOW)
        assert impact.active_commitment_microunits == 500_000
        assert impact.committed_over_new_cap_microunits == 100_000
        assert impact.requires_operator_attention
