from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, datetime
from itertools import combinations

import networkx as nx

from project_pipeline.domain.control import ControlSnapshot
from project_pipeline.domain.scheduler import (
    AdmissionDecision,
    AdmissionState,
    BackpressurePolicy,
    BackpressureSignals,
    LaneAssignment,
    ResourcePool,
    ResourceRegistrySnapshot,
    SchedulerPlan,
    SchedulerTaskProfile,
    scheduler_identifier,
)
from project_pipeline.lifecycle import claim_is_admissible
from project_pipeline.scheduler.backpressure import evaluate_backpressure
from project_pipeline.scheduler.conflicts import build_conflict_graph
from project_pipeline.scheduler.ortools_optimizer import (
    OrToolsOptimizerError,
    OrToolsSafeSetOptimizer,
)
from project_pipeline.scheduler.resources import add_claim_usage, admission_reasons, capacity_usage


class DynamicLaneScheduler:
    """Deterministically choose maximum-safe useful throughput from ready work."""

    def __init__(
        self,
        *,
        exact_candidate_limit: int = 18,
        ortools_optimizer: OrToolsSafeSetOptimizer | None = None,
    ) -> None:
        if exact_candidate_limit < 1:
            raise ValueError("exact candidate limit must be positive")
        self.exact_candidate_limit = exact_candidate_limit
        self.ortools_optimizer = ortools_optimizer or OrToolsSafeSetOptimizer()

    def plan(
        self,
        control: ControlSnapshot,
        profiles: Iterable[SchedulerTaskProfile],
        registry: ResourceRegistrySnapshot,
        *,
        signals: BackpressureSignals | None = None,
        backpressure_policy: BackpressurePolicy | None = None,
        max_lanes: int | None = None,
        now: datetime | None = None,
    ) -> SchedulerPlan:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        profile_by_id = {item.task_id: item for item in profiles}
        ready_ids = [item.task_id for item in control.sequence.ordered_ready_work]
        candidates = tuple(profile_by_id[item] for item in ready_ids if item in profile_by_id)
        decision = evaluate_backpressure(
            signals or BackpressureSignals(queue_depth=len(candidates)), backpressure_policy
        )

        natural_limit = (
            len(candidates) if max_lanes is None else max(0, min(max_lanes, len(candidates)))
        )
        lane_limit = min(natural_limit, math.floor(natural_limit * decision.lane_fraction))
        if (
            natural_limit > 0
            and decision.admit_new_work
            and decision.lane_fraction > 0
            and lane_limit == 0
        ):
            lane_limit = 1

        graph, conflicts = build_conflict_graph(candidates)
        pools = {pool.resource_key: pool for pool in registry.pools}
        base_usage = capacity_usage(registry, now)
        admissions: dict[str, AdmissionDecision] = {}
        prelim: list[SchedulerTaskProfile] = []
        for candidate in candidates:
            if not decision.admit_new_work:
                admissions[candidate.task_id] = AdmissionDecision(
                    task_id=candidate.task_id,
                    state=AdmissionState.BACKPRESSURE,
                    admitted=False,
                    reasons=(f"backpressure:{decision.mode.value}",),
                )
                continue
            if not candidate.policy_eligible:
                admissions[candidate.task_id] = AdmissionDecision(
                    task_id=candidate.task_id,
                    state=AdmissionState.POLICY_DENIED,
                    admitted=False,
                    reasons=("policy_denied",),
                )
                continue
            if not candidate.workspace_isolated:
                admissions[candidate.task_id] = AdmissionDecision(
                    task_id=candidate.task_id,
                    state=AdmissionState.WORKSPACE_UNSAFE,
                    admitted=False,
                    reasons=("workspace_not_isolated",),
                )
                continue
            path_claims = tuple(
                claim.resource_key for claim in candidate.claims if claim.resource_type.value == "PATH"
            )
            if path_claims and not claim_is_admissible(path_claims):
                admissions[candidate.task_id] = AdmissionDecision(
                    task_id=candidate.task_id,
                    state=AdmissionState.POLICY_DENIED,
                    admitted=False,
                    reasons=("pp327_owned_path_collision",),
                )
                continue
            reasons = admission_reasons(candidate.claims, registry, when=now)
            if reasons:
                state = (
                    AdmissionState.CAPACITY_EXHAUSTED
                    if any(item.startswith("capacity:") for item in reasons)
                    else AdmissionState.LEASE_UNAVAILABLE
                )
                admissions[candidate.task_id] = AdmissionDecision(
                    task_id=candidate.task_id, state=state, admitted=False, reasons=reasons
                )
                continue
            prelim.append(candidate)

        if lane_limit <= 0 or not prelim:
            selected: tuple[SchedulerTaskProfile, ...] = ()
            method = (
                "EXACT_BOUNDED"
                if len(prelim) <= self.exact_candidate_limit
                else "DETERMINISTIC_GREEDY"
            )
        elif len(prelim) <= self.exact_candidate_limit:
            selected = self._exact_select(prelim, graph, pools, base_usage, lane_limit)
            method = "EXACT_BOUNDED"
        elif self.ortools_optimizer.status().available:
            try:
                selected_ids = self.ortools_optimizer.select(
                    prelim, graph, pools, base_usage, lane_limit
                )
                selected = tuple(item for item in prelim if item.task_id in set(selected_ids))
                if not self._selection_is_valid(selected, graph, pools, base_usage, lane_limit):
                    raise OrToolsOptimizerError(
                        "OR-Tools selection failed Project Pipeline revalidation"
                    )
                method = "ORTOOLS_CP_SAT"
            except OrToolsOptimizerError:
                selected = self._greedy_select(prelim, graph, pools, base_usage, lane_limit)
                method = "DETERMINISTIC_GREEDY"
        else:
            selected = self._greedy_select(prelim, graph, pools, base_usage, lane_limit)
            method = "DETERMINISTIC_GREEDY"

        selected_ids = {item.task_id for item in selected}
        for candidate in prelim:
            if candidate.task_id in selected_ids:
                admissions[candidate.task_id] = AdmissionDecision(
                    task_id=candidate.task_id, state=AdmissionState.ADMITTED, admitted=True
                )
            else:
                conflict_selected = sorted(
                    item for item in graph.neighbors(candidate.task_id) if item in selected_ids
                )
                if conflict_selected:
                    admissions[candidate.task_id] = AdmissionDecision(
                        task_id=candidate.task_id,
                        state=AdmissionState.CONFLICT,
                        admitted=False,
                        reasons=tuple(f"conflicts_with:{item}" for item in conflict_selected),
                    )
                else:
                    admissions[candidate.task_id] = AdmissionDecision(
                        task_id=candidate.task_id,
                        state=AdmissionState.CAPACITY_EXHAUSTED,
                        admitted=False,
                        reasons=("lane_or_capacity_limit",),
                    )

        lanes = tuple(
            LaneAssignment(
                lane_id=scheduler_identifier("LANE", control.snapshot_id, item.task_id, str(index)),
                task_id=item.task_id,
                rank=index,
                utility_score=item.utility_score,
                claims=item.claims,
            )
            for index, item in enumerate(
                sorted(selected, key=lambda x: (x.sequence_rank, x.task_id)), start=1
            )
        )
        plan_identity = [
            control.snapshot_id,
            registry.registry_id,
            decision.mode.value,
            str(lane_limit),
            ",".join(lane.task_id for lane in lanes) or "none",
        ]
        return SchedulerPlan(
            plan_id=scheduler_identifier("SCHED", *plan_identity),
            project_id=control.project_id,
            control_snapshot_id=control.snapshot_id,
            registry_id=registry.registry_id,
            backpressure=decision,
            selection_method=method,
            candidate_count=len(candidates),
            lane_limit=lane_limit,
            lanes=lanes,
            conflicts=conflicts,
            admissions=tuple(
                admissions[item.task_id] for item in sorted(candidates, key=lambda x: x.task_id)
            ),
            generated_at_utc=now,
        )

    @staticmethod
    def _compatible(
        candidate: SchedulerTaskProfile, selected: tuple[SchedulerTaskProfile, ...], graph: nx.Graph
    ) -> bool:
        return all(not graph.has_edge(candidate.task_id, item.task_id) for item in selected)

    @staticmethod
    def _fits_capacity(
        candidate: SchedulerTaskProfile,
        selected: tuple[SchedulerTaskProfile, ...],
        pools: dict[str, ResourcePool],
        base_usage: dict[str, int],
    ) -> bool:
        usage = dict(base_usage)
        for item in selected:
            add_claim_usage(usage, item.claims, pools)
        for claim in candidate.claims:
            pool = pools.get(claim.resource_key)
            if pool and usage.get(claim.resource_key, 0) + claim.quantity > pool.allocatable_units:
                return False
        return True

    @classmethod
    def _selection_is_valid(
        cls,
        selected: tuple[SchedulerTaskProfile, ...],
        graph: nx.Graph,
        pools: dict[str, ResourcePool],
        base_usage: dict[str, int],
        lane_limit: int,
    ) -> bool:
        if len(selected) > lane_limit:
            return False
        if any(graph.has_edge(a.task_id, b.task_id) for a, b in combinations(selected, 2)):
            return False
        usage = dict(base_usage)
        for item in selected:
            for claim in item.claims:
                pool = pools.get(claim.resource_key)
                if (
                    pool
                    and usage.get(claim.resource_key, 0) + claim.quantity > pool.allocatable_units
                ):
                    return False
                if pool:
                    usage[claim.resource_key] = usage.get(claim.resource_key, 0) + claim.quantity
        return True

    def _exact_select(
        self,
        candidates: list[SchedulerTaskProfile],
        graph: nx.Graph,
        pools: dict[str, ResourcePool],
        base_usage: dict[str, int],
        lane_limit: int,
    ) -> tuple[SchedulerTaskProfile, ...]:
        ordered = tuple(sorted(candidates, key=lambda item: (item.sequence_rank, item.task_id)))
        best: tuple[SchedulerTaskProfile, ...] = ()
        best_key = (-1, -1, ())
        for size in range(1, min(lane_limit, len(ordered)) + 1):
            for combo in combinations(ordered, size):
                if any(graph.has_edge(a.task_id, b.task_id) for a, b in combinations(combo, 2)):
                    continue
                usage = dict(base_usage)
                valid = True
                for item in combo:
                    for claim in item.claims:
                        pool = pools.get(claim.resource_key)
                        if (
                            pool
                            and usage.get(claim.resource_key, 0) + claim.quantity
                            > pool.allocatable_units
                        ):
                            valid = False
                            break
                        if pool:
                            usage[claim.resource_key] = (
                                usage.get(claim.resource_key, 0) + claim.quantity
                            )
                    if not valid:
                        break
                if not valid:
                    continue
                # Maximize useful progress, then lane count, then stable lexical identity.
                score = sum(item.utility_score for item in combo)
                key = (score, len(combo), tuple(reversed(tuple(item.task_id for item in combo))))
                if key > best_key:
                    best_key = key
                    best = combo
        return best

    def _greedy_select(
        self,
        candidates: list[SchedulerTaskProfile],
        graph: nx.Graph,
        pools: dict[str, ResourcePool],
        base_usage: dict[str, int],
        lane_limit: int,
    ) -> tuple[SchedulerTaskProfile, ...]:
        ordered = sorted(
            candidates, key=lambda item: (-item.utility_score, item.sequence_rank, item.task_id)
        )
        selected: tuple[SchedulerTaskProfile, ...] = ()
        for candidate in ordered:
            if len(selected) >= lane_limit:
                break
            if self._compatible(candidate, selected, graph) and self._fits_capacity(
                candidate, selected, pools, base_usage
            ):
                selected = (*selected, candidate)
        return selected
