from __future__ import annotations

from collections.abc import Iterable

import networkx as nx

from project_pipeline.domain.scheduler import ConflictEdge, ResourceClaim, SchedulerTaskProfile


class SchedulerConflictError(ValueError):
    """Raised when scheduler conflict inputs are structurally invalid."""


def claims_conflict(left: ResourceClaim, right: ResourceClaim) -> bool:
    return left.conflicts_with(right)


def build_conflict_graph(
    profiles: Iterable[SchedulerTaskProfile],
) -> tuple[nx.Graph[str], tuple[ConflictEdge, ...]]:
    ordered = tuple(sorted(profiles, key=lambda item: item.task_id))
    by_id = {item.task_id: item for item in ordered}
    if len(by_id) != len(ordered):
        raise SchedulerConflictError("scheduler profiles contain duplicate task identifiers")

    graph: nx.Graph[str] = nx.Graph()
    graph.add_nodes_from(by_id)
    edges: list[ConflictEdge] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            reasons: set[str] = set()
            for left_claim in left.claims:
                for right_claim in right.claims:
                    if claims_conflict(left_claim, right_claim):
                        reasons.add(
                            f"{left_claim.resource_type.value}:{left_claim.resource_key}:"
                            f"{left_claim.access_mode.value}/{right_claim.access_mode.value}"
                        )
            if reasons:
                edge = ConflictEdge(
                    left_task_id=min(left.task_id, right.task_id),
                    right_task_id=max(left.task_id, right.task_id),
                    reasons=tuple(sorted(reasons)),
                )
                edges.append(edge)
                graph.add_edge(edge.left_task_id, edge.right_task_id, reasons=edge.reasons)
    return graph, tuple(sorted(edges, key=lambda item: (item.left_task_id, item.right_task_id)))
