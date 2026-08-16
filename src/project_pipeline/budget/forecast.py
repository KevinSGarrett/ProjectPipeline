from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, datetime

from project_pipeline.domain.budget import (
    BudgetForecast,
    BudgetLedgerEntry,
    BudgetPolicy,
    CostHistoryObservation,
    CostOutcomeMetrics,
    ForecastConfidence,
    LedgerDirection,
    budget_identifier,
)


def _nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[min(len(ordered) - 1, rank - 1)]


def build_cost_forecast(
    *,
    project_id: str,
    history: Iterable[CostHistoryObservation],
    task_class: str | None = None,
    provider_id: str | None = None,
    fallback_p50_microunits: int = 0,
    fallback_p90_microunits: int | None = None,
    queued_task_count: int = 0,
    burn_rate_microunits_per_day: int = 0,
    pace_ratio_milli: int = 1000,
    remaining_budget_microunits: int | None = None,
    policy: BudgetPolicy | None = None,
    now: datetime | None = None,
) -> BudgetForecast:
    policy = policy or BudgetPolicy()
    now = (now or datetime.now(UTC)).astimezone(UTC)
    rows = [
        item
        for item in history
        if (task_class is None or item.task_class == task_class)
        and (provider_id is None or item.provider_id == provider_id)
    ]
    costs = [item.cash_microunits + item.shadow_cost_microunits for item in rows]
    if costs:
        p50 = _nearest_rank(costs, 0.50)
        p90 = _nearest_rank(costs, 0.90)
        source = "HISTORICAL_OBSERVATIONS"
    else:
        p50 = max(0, fallback_p50_microunits)
        p90 = max(
            p50,
            fallback_p90_microunits
            if fallback_p90_microunits is not None
            else p50 * policy.default_p90_multiplier_milli // 1000,
        )
        source = "CALLER_ESTIMATE"
    sample_count = len(rows)
    if sample_count >= policy.minimum_history_samples_high:
        confidence = ForecastConfidence.HIGH
    elif sample_count >= policy.minimum_history_samples_medium:
        confidence = ForecastConfidence.MEDIUM
    else:
        confidence = ForecastConfidence.LOW
    queued_p50 = p50 * max(0, queued_task_count)
    queued_p90 = p90 * max(0, queued_task_count)
    runway = None
    if remaining_budget_microunits is not None and burn_rate_microunits_per_day > 0:
        runway = remaining_budget_microunits * 1000 // burn_rate_microunits_per_day
    return BudgetForecast(
        forecast_id=budget_identifier(
            "FORECAST", project_id, task_class or "*", provider_id or "*", now.isoformat()
        ),
        project_id=project_id,
        task_class=task_class,
        provider_id=provider_id,
        p50_microunits=p50,
        p90_microunits=p90,
        queued_p50_microunits=queued_p50,
        queued_p90_microunits=queued_p90,
        burn_rate_microunits_per_day=max(0, burn_rate_microunits_per_day),
        pace_ratio_milli=max(0, pace_ratio_milli),
        runway_days_milli=runway,
        sample_count=sample_count,
        confidence=confidence,
        source=source,
        generated_at_utc=now,
    )


def outcome_metrics(entries: Iterable[BudgetLedgerEntry]) -> CostOutcomeMetrics:
    rows = tuple(entries)
    total = sum(item.signed_cash_microunits for item in rows)
    debit_total = max(0, total)
    verified_ids = {item.outcome_id for item in rows if item.verified_outcome and item.outcome_id}
    merged_ids = {item.outcome_id for item in rows if item.merged_outcome and item.outcome_id}
    wasted = sum(
        item.cash_microunits
        for item in rows
        if item.direction is LedgerDirection.DEBIT and item.retry_waste
    )
    return CostOutcomeMetrics(
        total_cost_microunits=debit_total,
        verified_outcome_count=len(verified_ids),
        merged_outcome_count=len(merged_ids),
        wasted_cost_microunits=wasted,
        cost_per_verified_outcome_microunits=(debit_total // len(verified_ids))
        if verified_ids
        else None,
        cost_per_merged_outcome_microunits=(debit_total // len(merged_ids)) if merged_ids else None,
    )
