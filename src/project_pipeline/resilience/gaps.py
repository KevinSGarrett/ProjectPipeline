from __future__ import annotations

from typing import Any, Literal

from project_pipeline.domain.base import DomainModel
from project_pipeline.domain.resilience import FailureDomain
from project_pipeline.resilience.failover import RecoveryDirector, decide_operating_mode


class ProviderRemovalSimulation(DomainModel):
    provider_id: str
    isolated: Literal[True] = True
    live_mutation_performed: Literal[False] = False
    capability_coverage: tuple[str, ...]
    schedule_impact: str
    cost_impact: str
    blocked_work: tuple[str, ...]
    selected_substitute: str | None
    task_semantics_preserved: bool
    user_action_required: Literal[False] = False


class GpuWaitDecision(DomainModel):
    gpu_dependent_state: str
    independent_lanes_continue: bool
    recheck_owned: Literal[True] = True
    waiting_task_ids: tuple[str, ...]
    continuing_task_ids: tuple[str, ...]
    user_action_required: Literal[False] = False


def simulate_provider_removal(
    *,
    provider_id: str,
    required_capabilities: tuple[str, ...],
    providers: tuple[dict[str, Any], ...],
) -> ProviderRemovalSimulation:
    """Isolated provider-removal simulation. Does not disable a live paid service."""

    director = RecoveryDirector()
    remaining = tuple(item for item in providers if str(item.get("provider_id")) != provider_id)
    result = director.provider_substitution(required_capabilities, remaining)
    blocked = () if result.get("selected_provider_id") else required_capabilities
    return ProviderRemovalSimulation(
        provider_id=provider_id,
        capability_coverage=required_capabilities,
        schedule_impact="gpu-or-paid-dependent work waits; unrelated lanes continue",
        cost_impact="removed provider spend is zero in the isolated simulation",
        blocked_work=blocked,
        selected_substitute=str(result["selected_provider_id"])
        if result.get("selected_provider_id") is not None
        else None,
        task_semantics_preserved=bool(result.get("task_semantics_preserved")),
    )


def evaluate_gpu_wait(tasks: list[dict[str, Any]]) -> GpuWaitDecision:
    waiting = []
    continuing = []
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            continue
        if bool(task.get("gpu_required")):
            waiting.append(task_id)
        else:
            continuing.append(task_id)
    mode = decide_operating_mode((FailureDomain.GPU,), canonical_state_available=True)
    return GpuWaitDecision(
        gpu_dependent_state="WAITING_RESOURCES",
        independent_lanes_continue="deterministic_control" in mode.allowed_capabilities
        and "unaffected_capabilities" in mode.allowed_capabilities,
        waiting_task_ids=tuple(waiting),
        continuing_task_ids=tuple(continuing),
    )
