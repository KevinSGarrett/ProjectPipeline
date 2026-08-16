from datetime import UTC, datetime, timedelta

from project_pipeline.budget.forecast import build_cost_forecast, outcome_metrics
from project_pipeline.domain.budget import (
    BudgetLedgerEntry,
    CostClass,
    CostEvidenceState,
    CostHistoryObservation,
    ForecastConfidence,
    LedgerDirection,
    budget_identifier,
)

NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)


def history(i, cost):
    when = NOW + timedelta(minutes=i)
    return CostHistoryObservation(
        observation_id=budget_identifier(
            "HISTORY", "PROJECT-PIPELINE", f"PP-TASK-{i}", "provider:a", when.isoformat()
        ),
        project_id="PROJECT-PIPELINE",
        task_id=f"PP-TASK-{i}",
        task_class="code",
        provider_id="provider:a",
        cash_microunits=cost,
        succeeded=True,
        verified=True,
        observed_at_utc=when,
    )


def test_forecast_uses_historical_median_and_p90():
    rows = [history(i, cost) for i, cost in enumerate([10, 20, 30, 40, 100], 1)]
    result = build_cost_forecast(
        project_id="PROJECT-PIPELINE",
        history=rows,
        task_class="code",
        provider_id="provider:a",
        now=NOW,
    )
    assert result.p50_microunits == 30
    assert result.p90_microunits == 100
    assert result.confidence is ForecastConfidence.MEDIUM


def test_forecast_without_history_labels_caller_estimate_low_confidence():
    result = build_cost_forecast(
        project_id="PROJECT-PIPELINE",
        history=(),
        fallback_p50_microunits=100,
        fallback_p90_microunits=180,
        queued_task_count=3,
        now=NOW,
    )
    assert result.source == "CALLER_ESTIMATE"
    assert result.confidence is ForecastConfidence.LOW
    assert result.queued_p90_microunits == 540


def test_outcome_metrics_measure_verified_cost_and_waste():
    entries = []
    for key, cost, outcome, verified, waste in [
        ("a", 100, "OUT-1", True, False),
        ("b", 50, "OUT-1", True, True),
        ("c", 150, "OUT-2", True, False),
    ]:
        entries.append(
            BudgetLedgerEntry(
                entry_id=budget_identifier("ENTRY", key),
                idempotency_key=key,
                project_id="PROJECT-PIPELINE",
                task_id="PP-TASK-1",
                outcome_id=outcome,
                cost_class=CostClass.PROVIDER,
                direction=LedgerDirection.DEBIT,
                cash_microunits=cost,
                scope_keys=("GLOBAL:*",),
                evidence_state=CostEvidenceState.RECONCILED,
                verified_outcome=verified,
                retry_waste=waste,
                observed_at_utc=NOW,
                recorded_at_utc=NOW,
            )
        )
    metrics = outcome_metrics(entries)
    assert metrics.total_cost_microunits == 300
    assert metrics.verified_outcome_count == 2
    assert metrics.cost_per_verified_outcome_microunits == 150
    assert metrics.wasted_cost_microunits == 50
