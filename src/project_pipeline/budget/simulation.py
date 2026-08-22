from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.budget.persistence import BudgetStore
from project_pipeline.budget.service import BudgetGovernor
from project_pipeline.domain.budget import (
    BudgetAdmissionDecision,
    BudgetAdmissionRequest,
    BudgetLimit,
    BudgetPolicy,
    BudgetScopeType,
    BudgetSimulationResult,
    CostClass,
    CostEvidenceState,
    PressureMode,
    ReserveReason,
    SpendLease,
    budget_identifier,
)

_SCENARIOS = (
    "normal",
    "concurrent_reservation",
    "yellow_conservation",
    "red_reserve",
    "hard_stop_local_continues",
    "unknown_outcome",
)


def supported_scenarios() -> tuple[str, ...]:
    return _SCENARIOS


def _limit(cap: int, reserve: int = 0) -> BudgetLimit:
    return BudgetLimit(
        limit_id=budget_identifier("LIMIT", "GLOBAL:*", "monthly-test"),
        scope_type=BudgetScopeType.GLOBAL,
        scope_id="*",
        cycle_id="monthly-test",
        hard_cap_microunits=cap,
        soft_cap_microunits=max(0, cap - reserve),
        protected_reserve_microunits=reserve,
    )


def _request(
    task_id: str,
    p90: int,
    *,
    task_class: str = "implementation",
    provider_id: str | None = None,
    scope_keys: tuple[str, ...] = ("GLOBAL:*",),
    quota_requirements: dict[str, int] | None = None,
    priority: str = "P2",
    risk: str = "MEDIUM",
    critical_path: bool = False,
    required_verification: bool = False,
    paid_incremental: bool = True,
    local_or_subscription_alternative: bool = False,
    reserve_reason: ReserveReason | None = None,
    deadline_at_utc: datetime | None = None,
) -> BudgetAdmissionRequest:
    return BudgetAdmissionRequest(
        project_id="PROJECT-PIPELINE",
        task_id=task_id,
        task_class=task_class,
        provider_id=provider_id,
        scope_keys=scope_keys,
        estimated_p50_microunits=max(0, p90 * 2 // 3),
        estimated_p90_microunits=p90,
        quota_requirements=quota_requirements or {},
        priority=priority,
        risk=risk,
        critical_path=critical_path,
        required_verification=required_verification,
        paid_incremental=paid_incremental,
        local_or_subscription_alternative=local_or_subscription_alternative,
        reserve_reason=reserve_reason,
        deadline_at_utc=deadline_at_utc,
    )


def simulate_scenario(root: Path, scenario: str) -> BudgetSimulationResult:
    if scenario not in _SCENARIOS:
        raise ValueError(f"unsupported budget scenario: {scenario}")
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    admitted: list[str] = []
    denied: list[str] = []
    notes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="project-pipeline-budget-sim-") as temp:
        db = Path(temp) / "budget.db"
        with BudgetStore(db, root) as store:
            governor = BudgetGovernor(store, BudgetPolicy())
            governor.configure_limit(_limit(1_000_000, 200_000))

            def run(
                request: BudgetAdmissionRequest, key: str, forecast: int = 0, pace: int = 1000
            ) -> tuple[BudgetAdmissionDecision, SpendLease | None]:
                decision = governor.admit(
                    request,
                    cycle_id="monthly-test",
                    forecast_p90_microunits=forecast,
                    pace_ratio_milli=pace,
                    now=now,
                )
                if decision.admitted:
                    admitted.append(request.task_id)
                    if not request.paid_incremental and not request.quota_requirements:
                        return decision, None
                    lease = governor.reserve(
                        request, decision, cycle_id="monthly-test", idempotency_key=key, now=now
                    )
                    return decision, lease
                denied.append(request.task_id)
                return decision, None

            if scenario == "normal":
                decision, lease = run(_request("PP-TASK-900001", 100_000), "sim-normal")
                pressure = decision.pressure_mode
                notes.append(f"lease:{lease.lease_id if lease else 'none'}")
            elif scenario == "concurrent_reservation":
                first, _ = run(_request("PP-TASK-900002", 500_000), "sim-race-1")
                second, _ = run(_request("PP-TASK-900003", 400_000), "sim-race-2")
                pressure = max(
                    (first.pressure_mode, second.pressure_mode),
                    key=lambda x: list(PressureMode).index(x),
                )
                notes.append("atomic reservations prevent aggregate normal-budget overshoot")
            elif scenario == "yellow_conservation":
                decision, _ = run(
                    _request("PP-TASK-900004", 100_000), "sim-yellow", forecast=650_000, pace=1150
                )
                pressure = decision.pressure_mode
                notes.extend(decision.preferred_execution_modes)
            elif scenario == "red_reserve":
                decision, _ = run(
                    _request(
                        "PP-TASK-900005",
                        100_000,
                        priority="P0",
                        critical_path=True,
                        reserve_reason=ReserveReason.CRITICAL_PATH,
                    ),
                    "sim-red",
                    forecast=790_000,
                    pace=1500,
                )
                pressure = decision.pressure_mode
                notes.append(f"reserve_authorized:{decision.reserve_authorized}")
            elif scenario == "hard_stop_local_continues":
                _paid, paid_lease = run(_request("PP-TASK-900006", 800_000), "sim-hard-paid")
                if paid_lease:
                    entry = governor.make_usage_entry(
                        idempotency_key="sim-hard-settle",
                        project_id="PROJECT-PIPELINE",
                        task_id="PP-TASK-900006",
                        scope_keys=("GLOBAL:*",),
                        cost_class=CostClass.PROVIDER,
                        evidence_state=CostEvidenceState.RECONCILED,
                        cash_microunits=800_000,
                    )
                    governor.settle(paid_lease.lease_id, entry, now=now)
                reserve_req = _request(
                    "PP-TASK-900006R",
                    200_000,
                    priority="P0",
                    critical_path=True,
                    reserve_reason=ReserveReason.CRITICAL_PATH,
                )
                reserve_decision, reserve_lease = run(reserve_req, "sim-hard-reserve")
                if reserve_lease:
                    reserve_entry = governor.make_usage_entry(
                        idempotency_key="sim-hard-reserve-settle",
                        project_id="PROJECT-PIPELINE",
                        task_id="PP-TASK-900006R",
                        scope_keys=("GLOBAL:*",),
                        cost_class=CostClass.PROVIDER,
                        evidence_state=CostEvidenceState.RECONCILED,
                        cash_microunits=200_000,
                    )
                    governor.settle(reserve_lease.lease_id, reserve_entry, now=now)
                local_req = _request(
                    "PP-TASK-900007",
                    0,
                    paid_incremental=False,
                    local_or_subscription_alternative=True,
                )
                local, _ = run(local_req, "sim-hard-local")
                pressure = local.pressure_mode
                notes.extend(
                    (
                        f"reserve_authorized:{reserve_decision.reserve_authorized}",
                        f"local_admitted:{local.admitted}",
                    )
                )
            else:
                decision, lease = run(_request("PP-TASK-900008", 200_000), "sim-unknown")
                assert lease is not None
                governor.mark_unknown_outcome(lease.lease_id, now=now)
                held = store.get_lease(lease.lease_id)
                pressure = decision.pressure_mode
                notes.append(f"reservation_held:{bool(held and held.reservation_held)}")

            snapshot = store.snapshot(_limit(1_000_000, 200_000), policy=governor.policy, now=now)
            return BudgetSimulationResult(
                simulation_id=budget_identifier("SIM", scenario, now.isoformat()),
                scenario=scenario,
                pressure_mode=pressure,
                admitted_tasks=tuple(admitted),
                denied_tasks=tuple(denied),
                spent_microunits=snapshot.spent_microunits,
                committed_microunits=snapshot.committed_microunits,
                remaining_microunits=snapshot.remaining_total_microunits,
                notes=tuple(notes),
                generated_at_utc=now,
            )
