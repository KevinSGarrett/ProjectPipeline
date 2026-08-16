from __future__ import annotations

from collections.abc import Iterable, Mapping

from project_pipeline.domain.budget import BudgetAdmissionDecision, PressureMode
from project_pipeline.domain.scheduler import SchedulerTaskProfile


def apply_budget_admission_to_scheduler(
    profiles: Iterable[SchedulerTaskProfile],
    decisions: Mapping[str, BudgetAdmissionDecision],
) -> tuple[SchedulerTaskProfile, ...]:
    """Budget denial is another policy gate; it never makes an unsafe task schedulable."""
    result: list[SchedulerTaskProfile] = []
    for profile in profiles:
        decision = decisions.get(profile.task_id)
        if decision is None:
            result.append(profile)
            continue
        eligible = profile.policy_eligible and decision.admitted
        result.append(profile.model_copy(update={"policy_eligible": eligible}))
    return tuple(result)


def paid_lane_ceiling(configured_max_lanes: int, pressure: PressureMode) -> int:
    """Conservative paid-work parallelism ceiling; local-only work is governed separately."""
    configured = max(0, configured_max_lanes)
    if pressure is PressureMode.GREEN:
        return configured
    if pressure is PressureMode.YELLOW:
        return max(1, configured * 3 // 4) if configured else 0
    if pressure is PressureMode.ORANGE:
        return max(1, configured // 2) if configured else 0
    if pressure is PressureMode.RED:
        return 1 if configured else 0
    return 0
