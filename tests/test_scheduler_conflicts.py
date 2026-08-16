from __future__ import annotations

from project_pipeline.domain.scheduler import (
    AccessMode,
    ResourceClaim,
    ResourceType,
    SchedulerTaskProfile,
)
from project_pipeline.scheduler import build_conflict_graph


def profile(task_id: str, *claims: ResourceClaim) -> SchedulerTaskProfile:
    return SchedulerTaskProfile(
        task_id=task_id,
        project_id="PROJECT-PIPELINE",
        sequence_rank=int(task_id.rsplit("-", 1)[1]),
        utility_score=100,
        priority="P1",
        claims=claims,
    )


def test_conflict_graph_covers_paths_ports_gpu_and_environment() -> None:
    a = profile(
        "PP-TASK-000001", ResourceClaim(resource_key="src/auth", resource_type=ResourceType.PATH)
    )
    b = profile(
        "PP-TASK-000002",
        ResourceClaim(resource_key="src/auth/token.py", resource_type=ResourceType.PATH),
    )
    c = profile(
        "PP-TASK-000003",
        ResourceClaim(resource_key="port:localhost:8001", resource_type=ResourceType.PORT),
    )
    d = profile(
        "PP-TASK-000004",
        ResourceClaim(resource_key="port:localhost:8001", resource_type=ResourceType.PORT),
    )
    e = profile(
        "PP-TASK-000005",
        ResourceClaim(resource_key="gpu:worker-01:0", resource_type=ResourceType.GPU),
    )
    f = profile(
        "PP-TASK-000006",
        ResourceClaim(resource_key="gpu:worker-01:0", resource_type=ResourceType.GPU),
    )
    g = profile(
        "PP-TASK-000007",
        ResourceClaim(resource_key="environment:staging", resource_type=ResourceType.ENVIRONMENT),
    )
    h = profile(
        "PP-TASK-000008",
        ResourceClaim(resource_key="environment:staging", resource_type=ResourceType.ENVIRONMENT),
    )
    graph, edges = build_conflict_graph((a, b, c, d, e, f, g, h))
    assert graph.has_edge(a.task_id, b.task_id)
    assert graph.has_edge(c.task_id, d.task_id)
    assert graph.has_edge(e.task_id, f.task_id)
    assert graph.has_edge(g.task_id, h.task_id)
    assert len(edges) == 4


def test_shared_capacity_claims_do_not_create_conflict_edge() -> None:
    def claim():
        return ResourceClaim(
            resource_key="machine:local/cpu_slots",
            resource_type=ResourceType.CPU_SLOT,
            access_mode=AccessMode.SHARED,
        )

    graph, edges = build_conflict_graph(
        (profile("PP-TASK-000001", claim()), profile("PP-TASK-000002", claim()))
    )
    assert not graph.has_edge("PP-TASK-000001", "PP-TASK-000002")
    assert not edges
