from datetime import UTC, datetime

from project_pipeline.budget.policy import BudgetEvaluator, build_snapshot, quota_shadow_cost
from project_pipeline.domain.budget import (
    BudgetAdmissionRequest,
    BudgetPolicy,
    PressureMode,
    QuotaLimit,
    ReserveReason,
    budget_identifier,
)

NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)
POLICY = BudgetPolicy()


def snap(spent=0, committed=0, forecast=0, pace=1000):
    return build_snapshot(
        scope_key="GLOBAL:*",
        hard_cap_microunits=1_000_000,
        protected_reserve_microunits=200_000,
        spent_microunits=spent,
        credited_microunits=0,
        committed_microunits=committed,
        forecast_p90_microunits=forecast,
        pace_ratio_milli=pace,
        policy=POLICY,
        observed_at_utc=NOW,
    )


def req(cost=100_000, **kwargs):
    data = dict(
        project_id="PROJECT-PIPELINE",
        task_id="PP-TASK-1",
        task_class="implementation",
        scope_keys=("GLOBAL:*",),
        estimated_p50_microunits=cost * 2 // 3,
        estimated_p90_microunits=cost,
    )
    data.update(kwargs)
    return BudgetAdmissionRequest(**data)


def test_pressure_progresses_from_green_to_red():
    assert snap().pressure_mode is PressureMode.GREEN
    assert snap(forecast=650_000).pressure_mode is PressureMode.YELLOW
    assert snap(forecast=730_000).pressure_mode is PressureMode.ORANGE
    assert snap(forecast=790_000).pressure_mode is PressureMode.RED


def test_hard_stop_at_hard_cap():
    assert snap(spent=1_000_000).pressure_mode is PressureMode.HARD_STOP


def test_paid_work_requires_configured_limit_snapshot():
    decision = BudgetEvaluator(POLICY).evaluate(req(), ())
    assert not decision.admitted
    assert "budget_limit_missing" in decision.reasons


def test_red_pressure_blocks_noncritical_incremental_paid_work():
    decision = BudgetEvaluator(POLICY).evaluate(req(), (snap(forecast=790_000),), now=NOW)
    assert not decision.admitted
    assert "red_pressure_requires_reserve_or_required_verification" in decision.reasons


def test_red_pressure_allows_authorized_critical_reserve():
    request = req(
        priority="P0",
        critical_path=True,
        reserve_reason=ReserveReason.CRITICAL_PATH,
    )
    decision = BudgetEvaluator(POLICY).evaluate(
        request, (snap(spent=750_000, forecast=40_000),), now=NOW
    )
    assert decision.admitted
    assert decision.reserve_authorized


def test_hard_stop_still_allows_non_paid_local_work():
    request = req(cost=0, paid_incremental=False, local_or_subscription_alternative=True)
    decision = BudgetEvaluator(POLICY).evaluate(request, (snap(spent=1_000_000),), now=NOW)
    assert decision.admitted
    assert not decision.allowed_paid_incremental


def test_quota_shadow_cost_rises_as_quota_depletes():
    quota = QuotaLimit(
        quota_id=budget_identifier("QUOTA", "PROJECT:PROJECT-PIPELINE", "provider:test", "tokens"),
        scope_key="PROJECT:PROJECT-PIPELINE",
        provider_id="provider:test",
        quota_name="tokens",
        capacity_units=1000,
        max_shadow_cost_microunits=1_000_000,
    )
    assert (
        quota_shadow_cost(quota, 100)
        < quota_shadow_cost(quota, 500)
        < quota_shadow_cost(quota, 900)
    )
