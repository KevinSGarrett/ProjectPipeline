from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import Any

import networkx as nx

from project_pipeline.domain.scheduler import ResourcePool, SchedulerTaskProfile


class OrToolsOptimizerError(RuntimeError):
    """Raised when the optional OR-Tools optimizer cannot produce a valid result."""


@dataclass(frozen=True, slots=True)
class OrToolsOptimizerStatus:
    available: bool
    backend: str
    reason: str = ""


class OrToolsSafeSetOptimizer:
    """Optional CP-SAT optimizer behind Project Pipeline-owned scheduling semantics.

    OR-Tools chooses a candidate set only. Project Pipeline revalidates conflicts,
    capacity, and lane limits before accepting the result.
    """

    def __init__(
        self, cp_model_module: Any | None = None, *, max_time_seconds: float = 2.0
    ) -> None:
        self._cp_model = cp_model_module
        self.max_time_seconds = max_time_seconds

    def _module(self) -> Any:
        if self._cp_model is not None:
            return self._cp_model
        try:
            return import_module("ortools.sat.python.cp_model")
        except ImportError as error:
            raise OrToolsOptimizerError("OR-Tools is not installed") from error

    def status(self) -> OrToolsOptimizerStatus:
        try:
            self._module()
        except OrToolsOptimizerError as error:
            return OrToolsOptimizerStatus(False, "OR-Tools CP-SAT", str(error))
        return OrToolsOptimizerStatus(True, "OR-Tools CP-SAT")

    def select(
        self,
        candidates: Iterable[SchedulerTaskProfile],
        graph: nx.Graph[str],
        pools: dict[str, ResourcePool],
        base_usage: dict[str, int],
        lane_limit: int,
    ) -> tuple[str, ...]:
        cp_model = self._module()
        ordered = tuple(sorted(candidates, key=lambda item: (item.sequence_rank, item.task_id)))
        if not ordered or lane_limit <= 0:
            return ()

        model = cp_model.CpModel()
        variables = {
            item.task_id: model.NewBoolVar(f"lane_{index}") for index, item in enumerate(ordered)
        }
        model.Add(sum(variables.values()) <= lane_limit)
        for left, right in sorted(graph.edges()):
            if left in variables and right in variables:
                model.Add(variables[left] + variables[right] <= 1)

        for resource_key, pool in sorted(pools.items()):
            available = max(0, pool.allocatable_units - base_usage.get(resource_key, 0))
            terms = []
            for item in ordered:
                quantity = sum(
                    claim.quantity for claim in item.claims if claim.resource_key == resource_key
                )
                if quantity:
                    terms.append(quantity * variables[item.task_id])
            if terms:
                model.Add(sum(terms) <= available)

        # Utility dominates. The lane bonus prefers useful concurrency, and the
        # stable lexical term makes ties repeatable without transferring authority.
        utility_scale = 1_000_000
        lane_bonus = 1_000
        stable_bonus = {item.task_id: len(ordered) - index for index, item in enumerate(ordered)}
        model.Maximize(
            sum(
                (
                    round(item.utility_score * 1000) * utility_scale
                    + lane_bonus
                    + stable_bonus[item.task_id]
                )
                * variables[item.task_id]
                for item in ordered
            )
        )

        solver = cp_model.CpSolver()
        if hasattr(solver, "parameters"):
            solver.parameters.num_search_workers = 1
            solver.parameters.random_seed = 0
            solver.parameters.max_time_in_seconds = self.max_time_seconds
        status = solver.Solve(model)
        accepted = {getattr(cp_model, "OPTIMAL", None), getattr(cp_model, "FEASIBLE", None)}
        if status not in accepted:
            raise OrToolsOptimizerError(f"CP-SAT returned unsupported status {status}")
        return tuple(item.task_id for item in ordered if solver.Value(variables[item.task_id]))
