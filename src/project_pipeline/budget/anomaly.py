from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from project_pipeline.domain.budget import (
    BudgetAnomaly,
    BudgetChangeImpact,
    BudgetLimit,
    BudgetPolicy,
    SpendLease,
    budget_identifier,
)


def detect_cost_anomaly(
    *,
    project_id: str,
    expected_p90_microunits: int,
    observed_microunits: int,
    policy: BudgetPolicy | None = None,
    task_id: str | None = None,
    provider_id: str | None = None,
    now: datetime | None = None,
) -> BudgetAnomaly:
    policy = policy or BudgetPolicy()
    now = (now or datetime.now(UTC)).astimezone(UTC)
    reasons: list[str] = []
    if expected_p90_microunits <= 0:
        ratio = 1_000_000 if observed_microunits > 0 else 0
        severity = "BLOCK" if observed_microunits > 0 else "NORMAL"
        if observed_microunits > 0:
            reasons.append("unexpected_paid_cost_without_estimate")
    else:
        ratio = max(0, observed_microunits) * 1000 // expected_p90_microunits
        if ratio >= policy.anomaly_block_ratio_milli:
            severity = "BLOCK"
            reasons.append("observed_cost_exceeds_runaway_threshold")
        elif ratio >= policy.anomaly_warn_ratio_milli:
            severity = "WARN"
            reasons.append("observed_cost_exceeds_expected_p90")
        else:
            severity = "NORMAL"
    return BudgetAnomaly(
        anomaly_id=budget_identifier(
            "ANOMALY",
            project_id,
            task_id or "*",
            provider_id or "*",
            str(expected_p90_microunits),
            str(observed_microunits),
            now.isoformat(),
        ),
        project_id=project_id,
        task_id=task_id,
        provider_id=provider_id,
        expected_p90_microunits=max(0, expected_p90_microunits),
        observed_microunits=max(0, observed_microunits),
        observed_to_expected_milli=ratio,
        severity=severity,
        block_new_paid_work=severity == "BLOCK",
        reasons=tuple(reasons),
        detected_at_utc=now,
    )


def analyze_limit_change(
    old_limit: BudgetLimit,
    new_limit: BudgetLimit,
    active_leases: Iterable[SpendLease],
    *,
    now: datetime | None = None,
) -> BudgetChangeImpact:
    if old_limit.scope_key != new_limit.scope_key or old_limit.cycle_id != new_limit.cycle_id:
        raise ValueError("budget change impact requires the same scope and cycle")
    now = (now or datetime.now(UTC)).astimezone(UTC)
    leases = tuple(
        item
        for item in active_leases
        if old_limit.scope_key in item.scope_keys and item.reservation_held
    )
    committed = sum(item.reserved_microunits for item in leases)
    over = max(0, committed - new_limit.hard_cap_microunits)
    return BudgetChangeImpact(
        impact_id=budget_identifier(
            "IMPACT",
            old_limit.scope_key,
            old_limit.cycle_id,
            str(old_limit.hard_cap_microunits),
            str(new_limit.hard_cap_microunits),
            now.isoformat(),
        ),
        scope_key=old_limit.scope_key,
        old_hard_cap_microunits=old_limit.hard_cap_microunits,
        new_hard_cap_microunits=new_limit.hard_cap_microunits,
        active_commitment_microunits=committed,
        committed_over_new_cap_microunits=over,
        active_lease_count=len(leases),
        requires_operator_attention=over > 0
        or new_limit.hard_cap_microunits < old_limit.hard_cap_microunits,
        generated_at_utc=now,
    )
