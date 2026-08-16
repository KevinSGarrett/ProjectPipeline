from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from project_pipeline.domain.budget import (
    BudgetAdmissionDecision,
    BudgetAdmissionRequest,
    BudgetPolicy,
    BudgetSnapshot,
    PressureMode,
    QuotaLimit,
    ReserveReason,
    budget_fingerprint,
    budget_identifier,
)

_PRESSURE_ORDER = {
    PressureMode.GREEN: 0,
    PressureMode.YELLOW: 1,
    PressureMode.ORANGE: 2,
    PressureMode.RED: 3,
    PressureMode.HARD_STOP: 4,
}


def quota_shadow_cost(limit: QuotaLimit, used_or_reserved_units: int) -> int:
    """Monotonic quota scarcity price; it never becomes a cash charge."""
    used = max(0, min(used_or_reserved_units, limit.capacity_units))
    remaining = limit.capacity_units - used
    depletion_milli = 1000 - (remaining * 1000 // limit.capacity_units)
    return limit.max_shadow_cost_microunits * depletion_milli * depletion_milli // 1_000_000


def determine_pressure(
    *,
    policy: BudgetPolicy,
    hard_cap_microunits: int,
    protected_reserve_microunits: int,
    soft_cap_microunits: int | None = None,
    spent_microunits: int,
    credited_microunits: int,
    committed_microunits: int,
    forecast_p90_microunits: int,
    pace_ratio_milli: int,
) -> PressureMode:
    effective_spent = max(0, spent_microunits - credited_microunits)
    committed_total = effective_spent + committed_microunits
    if hard_cap_microunits == 0:
        return PressureMode.HARD_STOP if committed_total > 0 else PressureMode.GREEN
    if committed_total >= hard_cap_microunits:
        return PressureMode.HARD_STOP
    normal_cap = max(0, hard_cap_microunits - protected_reserve_microunits)
    projected = committed_total + forecast_p90_microunits
    configured_soft = (
        normal_cap if soft_cap_microunits is None else min(normal_cap, max(0, soft_cap_microunits))
    )
    denominator = (
        configured_soft
        if configured_soft > 0
        else (normal_cap if normal_cap > 0 else hard_cap_microunits)
    )
    projected_ratio = projected * 1000 // max(1, denominator)
    if projected_ratio >= 1000:
        # Normal budget is exhausted but protected reserve still exists.
        mode = PressureMode.RED
    elif projected_ratio >= policy.red_projected_ratio_milli:
        mode = PressureMode.RED
    elif projected_ratio >= policy.orange_projected_ratio_milli:
        mode = PressureMode.ORANGE
    elif projected_ratio >= policy.yellow_projected_ratio_milli:
        mode = PressureMode.YELLOW
    else:
        mode = PressureMode.GREEN
    if pace_ratio_milli >= policy.red_pace_ratio_milli:
        pace_mode = PressureMode.RED
    elif pace_ratio_milli >= policy.orange_pace_ratio_milli:
        pace_mode = PressureMode.ORANGE
    elif pace_ratio_milli >= policy.yellow_pace_ratio_milli:
        pace_mode = PressureMode.YELLOW
    else:
        pace_mode = PressureMode.GREEN
    return max((mode, pace_mode), key=lambda item: _PRESSURE_ORDER[item])


def build_snapshot(
    *,
    scope_key: str,
    hard_cap_microunits: int,
    protected_reserve_microunits: int,
    soft_cap_microunits: int | None = None,
    spent_microunits: int,
    credited_microunits: int,
    committed_microunits: int,
    forecast_p90_microunits: int,
    pace_ratio_milli: int,
    policy: BudgetPolicy,
    observed_at_utc: datetime | None = None,
) -> BudgetSnapshot:
    observed_at_utc = (observed_at_utc or datetime.now(UTC)).astimezone(UTC)
    effective = max(0, spent_microunits - credited_microunits)
    used = effective + committed_microunits
    normal_cap = max(0, hard_cap_microunits - protected_reserve_microunits)
    return BudgetSnapshot(
        scope_key=scope_key,
        hard_cap_microunits=hard_cap_microunits,
        soft_cap_microunits=min(
            max(0, hard_cap_microunits - protected_reserve_microunits),
            max(
                0,
                soft_cap_microunits
                if soft_cap_microunits is not None
                else hard_cap_microunits - protected_reserve_microunits,
            ),
        ),
        protected_reserve_microunits=protected_reserve_microunits,
        spent_microunits=spent_microunits,
        credited_microunits=credited_microunits,
        committed_microunits=committed_microunits,
        remaining_normal_microunits=max(0, normal_cap - used),
        remaining_total_microunits=max(0, hard_cap_microunits - used),
        forecast_p90_microunits=forecast_p90_microunits,
        pace_ratio_milli=pace_ratio_milli,
        pressure_mode=determine_pressure(
            policy=policy,
            hard_cap_microunits=hard_cap_microunits,
            protected_reserve_microunits=protected_reserve_microunits,
            soft_cap_microunits=soft_cap_microunits,
            spent_microunits=spent_microunits,
            credited_microunits=credited_microunits,
            committed_microunits=committed_microunits,
            forecast_p90_microunits=forecast_p90_microunits,
            pace_ratio_milli=pace_ratio_milli,
        ),
        observed_at_utc=observed_at_utc,
    )


class BudgetEvaluator:
    """Deterministic admission policy over canonical budget and quota snapshots."""

    def __init__(self, policy: BudgetPolicy | None = None) -> None:
        self.policy = policy or BudgetPolicy()

    def evaluate(
        self,
        request: BudgetAdmissionRequest,
        snapshots: Iterable[BudgetSnapshot],
        quota_limits: Mapping[str, QuotaLimit] | None = None,
        quota_used_or_reserved: Mapping[str, int] | None = None,
        *,
        now: datetime | None = None,
    ) -> BudgetAdmissionDecision:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        snapshots = tuple(snapshots)
        quota_limits = quota_limits or {}
        quota_used_or_reserved = quota_used_or_reserved or {}
        reasons: list[str] = []
        modes = [item.pressure_mode for item in snapshots] or [PressureMode.GREEN]
        pressure = max(modes, key=lambda item: _PRESSURE_ORDER[item])

        reserve_authorized = request.reserve_reason is not None and request.reserve_reason in set(
            self.policy.reserve_reasons
        )
        if request.reserve_reason is not None and not reserve_authorized:
            reasons.append("reserve_reason_not_authorized")
        deadline_protection = (
            request.reserve_reason is ReserveReason.DEADLINE_PROTECTION
            and request.deadline_at_utc is not None
        )
        if reserve_authorized and not (
            request.critical_path
            or request.required_verification
            or request.priority in {"P0", "P1"}
            or deadline_protection
        ):
            reserve_authorized = False
            reasons.append("protected_reserve_requires_critical_work")

        if not request.paid_incremental:
            paid_allowed = False
            monetary_authorized = 0
        elif not snapshots:
            paid_allowed = False
            monetary_authorized = 0
            reasons.append("budget_limit_missing")
        else:
            paid_allowed = pressure is not PressureMode.HARD_STOP
            available = [
                item.remaining_total_microunits
                if reserve_authorized
                else item.remaining_normal_microunits
                for item in snapshots
            ]
            monetary_authorized = min([request.estimated_p90_microunits, *available])
            if request.estimated_p90_microunits > monetary_authorized:
                reasons.append("insufficient_budget_for_p90")

        if pressure is PressureMode.HARD_STOP and request.paid_incremental:
            reasons.append("hard_stop_blocks_incremental_paid_work")
        elif (
            pressure is PressureMode.RED
            and request.paid_incremental
            and not (reserve_authorized or request.required_verification)
        ):
            paid_allowed = False
            reasons.append("red_pressure_requires_reserve_or_required_verification")

        quota_shadow = 0
        quota_ok = True
        for quota_id, requested_units in request.quota_requirements.items():
            limit = quota_limits.get(quota_id)
            if limit is None or not limit.enabled:
                quota_ok = False
                reasons.append(f"quota_limit_missing:{quota_id}")
                continue
            used = max(0, quota_used_or_reserved.get(quota_id, 0))
            protected = 0 if reserve_authorized else limit.protected_units
            allocatable = max(0, limit.capacity_units - protected - used)
            if requested_units > allocatable:
                quota_ok = False
                reasons.append(f"quota_insufficient:{quota_id}")
            quota_shadow += quota_shadow_cost(limit, used + requested_units)

        monetary_ok = (not request.paid_incremental) or (
            paid_allowed and request.estimated_p90_microunits <= monetary_authorized
        )
        admitted = monetary_ok and quota_ok and "reserve_reason_not_authorized" not in reasons
        if not admitted and request.local_or_subscription_alternative:
            reasons.append("retry_with_local_or_subscription_alternative")

        preferred_modes: tuple[str, ...]
        if pressure is PressureMode.GREEN:
            preferred_modes = ("BEST_CAPABLE",)
        elif pressure is PressureMode.YELLOW:
            preferred_modes = ("LOWER_COST_CAPABLE", "SUBSCRIPTION", "LOCAL")
        elif pressure is PressureMode.ORANGE:
            preferred_modes = ("SUBSCRIPTION", "LOCAL", "LOWER_COST_CAPABLE")
        else:
            preferred_modes = ("LOCAL", "SUBSCRIPTION")

        fingerprint = budget_fingerprint(request.model_dump(mode="json"))
        return BudgetAdmissionDecision(
            decision_id=budget_identifier("ADMISSION", request.task_id, fingerprint),
            task_id=request.task_id,
            admitted=admitted,
            pressure_mode=pressure,
            authorized_microunits=monetary_authorized
            if admitted and request.paid_incremental
            else 0,
            reserve_authorized=reserve_authorized and admitted,
            allowed_paid_incremental=paid_allowed and admitted,
            quota_shadow_cost_microunits=quota_shadow,
            reasons=tuple(sorted(dict.fromkeys(reasons))),
            preferred_execution_modes=preferred_modes,
            generated_at_utc=now,
        )


def rebalance_provider_soft_envelopes(
    *,
    global_limit_microunits: int,
    provider_hard_caps: Mapping[str, int],
    demand_microunits: Mapping[str, int],
) -> dict[str, int]:
    """Deterministic capped weighted allocation; it only reallocates soft envelopes."""
    providers = sorted(provider_hard_caps)
    remaining = max(0, global_limit_microunits)
    result = {provider: 0 for provider in providers}
    active = set(providers)
    while remaining > 0 and active:
        total_weight = sum(max(1, demand_microunits.get(provider, 0)) for provider in active)
        progress = 0
        shares: dict[str, int] = {}
        for provider in sorted(active):
            capacity = max(0, provider_hard_caps[provider] - result[provider])
            if capacity <= 0:
                continue
            weight = max(1, demand_microunits.get(provider, 0))
            share = max(1, remaining * weight // max(1, total_weight))
            shares[provider] = min(capacity, share)
        for provider in sorted(shares):
            if remaining <= 0:
                break
            amount = min(shares[provider], remaining)
            result[provider] += amount
            remaining -= amount
            progress += amount
        active = {p for p in active if result[p] < max(0, provider_hard_caps[p])}
        if progress == 0:
            break
    return result


def reserve_reason_for_required_work(
    *, priority: str, critical_path: bool, required_verification: bool
) -> ReserveReason | None:
    if required_verification:
        return ReserveReason.REQUIRED_VERIFICATION
    if priority == "P0":
        return ReserveReason.P0_FAILURE_RECOVERY
    if critical_path:
        return ReserveReason.CRITICAL_PATH
    return None
