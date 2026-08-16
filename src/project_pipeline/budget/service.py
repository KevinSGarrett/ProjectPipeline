from __future__ import annotations

from datetime import UTC, datetime

from project_pipeline.budget.anomaly import analyze_limit_change, detect_cost_anomaly
from project_pipeline.budget.forecast import build_cost_forecast, outcome_metrics
from project_pipeline.budget.persistence import BudgetStore
from project_pipeline.budget.policy import BudgetEvaluator
from project_pipeline.domain.agents import NormalizedUsage
from project_pipeline.domain.budget import (
    BudgetAdmissionDecision,
    BudgetAdmissionRequest,
    BudgetAnomaly,
    BudgetChangeImpact,
    BudgetForecast,
    BudgetLedgerEntry,
    BudgetLimit,
    BudgetPolicy,
    CostClass,
    CostEvidenceState,
    CostHistoryObservation,
    CostOutcomeMetrics,
    LedgerDirection,
    QuotaLimit,
    SpendLease,
    SpendLeaseState,
    budget_identifier,
)


class BudgetGovernor:
    """Canonical budget authority over cost evidence, reservations, settlement, and pressure."""

    def __init__(self, store: BudgetStore, policy: BudgetPolicy | None = None) -> None:
        self.store = store
        self.policy = policy or BudgetPolicy()
        self.evaluator = BudgetEvaluator(self.policy)

    def configure_limit(self, limit: BudgetLimit) -> None:
        self.store.put_limit(limit)

    def configure_quota(self, limit: QuotaLimit) -> None:
        self.store.put_quota_limit(limit)

    def admit(
        self,
        request: BudgetAdmissionRequest,
        *,
        cycle_id: str,
        forecast_p90_microunits: int = 0,
        pace_ratio_milli: int = 1000,
        now: datetime | None = None,
    ) -> BudgetAdmissionDecision:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        snapshots = self.store.snapshots_for_request(
            request,
            cycle_id=cycle_id,
            policy=self.policy,
            forecast_p90_microunits=forecast_p90_microunits,
            pace_ratio_milli=pace_ratio_milli,
            now=now,
        )
        quota_limits = {item.quota_id: item for item in self.store.list_quota_limits()}
        quota_used = {
            quota_id: self.store.quota_used_or_reserved(quota_id, now=now)
            for quota_id in request.quota_requirements
        }
        decision = self.evaluator.evaluate(request, snapshots, quota_limits, quota_used, now=now)
        self.store.save_decision(decision)
        return decision

    def reserve(
        self,
        request: BudgetAdmissionRequest,
        decision: BudgetAdmissionDecision,
        *,
        cycle_id: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> SpendLease:
        return self.store.reserve(
            request,
            decision,
            cycle_id=cycle_id,
            idempotency_key=idempotency_key,
            policy=self.policy,
            now=now,
        )

    def make_usage_entry(
        self,
        *,
        idempotency_key: str,
        project_id: str,
        task_id: str | None,
        scope_keys: tuple[str, ...],
        cost_class: CostClass,
        evidence_state: CostEvidenceState,
        cash_microunits: int,
        provider_id: str | None = None,
        model_id: str | None = None,
        resource_id: str | None = None,
        tool_id: str | None = None,
        outcome_id: str | None = None,
        usage: NormalizedUsage | None = None,
        quota_units: dict[str, int] | None = None,
        shadow_cost_microunits: int = 0,
        verified_outcome: bool = False,
        merged_outcome: bool = False,
        retry_waste: bool = False,
        evidence_references: tuple[str, ...] = (),
        observed_at_utc: datetime | None = None,
    ) -> BudgetLedgerEntry:
        now = datetime.now(UTC)
        observed = (observed_at_utc or now).astimezone(UTC)
        dimensions: dict[str, int] = {}
        if usage is not None:
            dimensions = {
                "input_units": usage.input_units,
                "output_units": usage.output_units,
                "cached_input_units": usage.cached_input_units,
                "request_count": usage.request_count,
            }
        return BudgetLedgerEntry(
            entry_id=budget_identifier("ENTRY", idempotency_key),
            idempotency_key=idempotency_key,
            project_id=project_id,
            task_id=task_id,
            provider_id=provider_id,
            model_id=model_id,
            resource_id=resource_id,
            tool_id=tool_id,
            outcome_id=outcome_id,
            cost_class=cost_class,
            direction=LedgerDirection.DEBIT,
            cash_microunits=max(0, cash_microunits),
            shadow_cost_microunits=max(0, shadow_cost_microunits),
            quota_units=quota_units or {},
            usage_dimensions=dimensions,
            scope_keys=scope_keys,
            evidence_state=evidence_state,
            verified_outcome=verified_outcome,
            merged_outcome=merged_outcome,
            retry_waste=retry_waste,
            evidence_references=evidence_references,
            observed_at_utc=observed,
            recorded_at_utc=now,
        )

    def settle(
        self, lease_id: str, entry: BudgetLedgerEntry, *, now: datetime | None = None
    ) -> SpendLease:
        return self.store.settle_lease(lease_id, entry, now=now)

    def mark_unknown_outcome(self, lease_id: str, *, now: datetime | None = None) -> SpendLease:
        return self.store.mark_unknown_outcome(lease_id, now=now)

    def reconcile_unknown(
        self,
        lease_id: str,
        *,
        remote_effect_occurred: bool,
        entry: BudgetLedgerEntry | None = None,
        now: datetime | None = None,
    ) -> SpendLease:
        lease = self.store.get_lease(lease_id)
        if lease is None:
            raise KeyError(f"unknown budget lease: {lease_id}")
        if lease.state is not SpendLeaseState.UNKNOWN_OUTCOME:
            raise ValueError("only unknown-outcome leases require reconciliation")
        if remote_effect_occurred:
            if entry is None:
                raise ValueError(
                    "reconciliation requires observed cost evidence when remote effect occurred"
                )
            return self.store.settle_lease(lease_id, entry, now=now)
        if entry is not None:
            raise ValueError("no-cost reconciliation must not include a spend entry")
        # Explicit reconciliation that the remote effect did not occur releases the held reservation.
        return self.store.resolve_unknown_no_effect(lease_id, now=now)

    def detect_anomaly(
        self,
        *,
        project_id: str,
        expected_p90_microunits: int,
        observed_microunits: int,
        task_id: str | None = None,
        provider_id: str | None = None,
        now: datetime | None = None,
    ) -> BudgetAnomaly:
        anomaly = detect_cost_anomaly(
            project_id=project_id,
            expected_p90_microunits=expected_p90_microunits,
            observed_microunits=observed_microunits,
            policy=self.policy,
            task_id=task_id,
            provider_id=provider_id,
            now=now,
        )
        self.store.save_anomaly(anomaly)
        return anomaly

    def analyze_limit_change(
        self, old_limit: BudgetLimit, new_limit: BudgetLimit, *, now: datetime | None = None
    ) -> BudgetChangeImpact:
        return analyze_limit_change(
            old_limit, new_limit, self.store.list_active_leases(now=now), now=now
        )

    def lease_requires_reevaluation(
        self, lease: SpendLease, observed_consumed_microunits: int
    ) -> bool:
        if lease.reserved_microunits <= 0:
            return False
        consumed_milli = max(0, observed_consumed_microunits) * 1000 // lease.reserved_microunits
        return consumed_milli >= self.policy.reevaluate_at_consumed_milli

    def forecast(
        self,
        *,
        project_id: str,
        task_class: str | None = None,
        provider_id: str | None = None,
        fallback_p50_microunits: int = 0,
        fallback_p90_microunits: int | None = None,
        queued_task_count: int = 0,
        burn_rate_microunits_per_day: int = 0,
        pace_ratio_milli: int = 1000,
        remaining_budget_microunits: int | None = None,
        now: datetime | None = None,
    ) -> BudgetForecast:
        result = build_cost_forecast(
            project_id=project_id,
            history=self.store.list_history(project_id=project_id),
            task_class=task_class,
            provider_id=provider_id,
            fallback_p50_microunits=fallback_p50_microunits,
            fallback_p90_microunits=fallback_p90_microunits,
            queued_task_count=queued_task_count,
            burn_rate_microunits_per_day=burn_rate_microunits_per_day,
            pace_ratio_milli=pace_ratio_milli,
            remaining_budget_microunits=remaining_budget_microunits,
            policy=self.policy,
            now=now,
        )
        self.store.save_forecast(result)
        return result

    def record_history(self, observation: CostHistoryObservation) -> None:
        self.store.save_history(observation)

    def outcome_metrics(self, project_id: str) -> CostOutcomeMetrics:
        return outcome_metrics(self.store.list_ledger(project_id=project_id))
