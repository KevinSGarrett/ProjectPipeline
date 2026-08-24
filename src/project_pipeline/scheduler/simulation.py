from __future__ import annotations

from collections.abc import Sequence

from project_pipeline.domain.control import ControlSnapshot
from project_pipeline.domain.scheduler import (
    BackpressureSignals,
    ResourceRegistrySnapshot,
    SchedulerSimulationResult,
    SchedulerTaskProfile,
    scheduler_identifier,
)
from project_pipeline.scheduler.engine import DynamicLaneScheduler


def simulate_scenario(
    *,
    name: str,
    control: ControlSnapshot,
    profiles: Sequence[SchedulerTaskProfile],
    registry: ResourceRegistrySnapshot,
    signals: BackpressureSignals | None,
    expected_lane_count: int | None = None,
) -> SchedulerSimulationResult:
    plan = DynamicLaneScheduler().plan(control, profiles, registry, signals=signals)
    findings = []
    passed = True
    if expected_lane_count is not None and len(plan.lanes) != expected_lane_count:
        passed = False
        findings.append(f"expected {expected_lane_count} lanes but observed {len(plan.lanes)}")
    return SchedulerSimulationResult(
        simulation_id=scheduler_identifier("SIM", name, plan.plan_id),
        scenario_name=name,
        plan=plan,
        expected_lane_count=expected_lane_count,
        assertions_passed=passed,
        findings=tuple(findings),
    )
