from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.lanes import LaneRegistry
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor
from project_pipeline.autonomy_runtime.windows_service import (
    AutonomyRuntimeWindowsService,
    build_paths,
)
from project_pipeline.command_center.models import (
    HealthDimension,
    HealthState,
    LiveWorkItem,
)
from project_pipeline.command_center.projections import CommandCenterProjectionService


def project_autonomy_runtime(
    *,
    supervisor_state: Path,
    lane_state: Path | None = None,
    service_root: Path | None = None,
    repository_root: Path | None = None,
    ready_task_ids: list[str] | None = None,
    provider_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    supervisor = PersistentSupervisor(supervisor_state, repository_root=repository_root)
    status = supervisor.status()
    next_task = supervisor.select_next_work(ready_task_ids or [])
    supervisor.close()
    incidents: list[Any] = []
    if lane_state is not None and lane_state.exists():
        registry = LaneRegistry(lane_state)
        incidents = registry.list_incidents()
        registry.close()
    service_health = None
    if service_root is not None:
        service_health = AutonomyRuntimeWindowsService(build_paths(root=service_root)).health()
    live_work = [
        LiveWorkItem(
            work_id=str(item["operation_id"]),
            title=str(item["task_id"]),
            state=str(item["state"]),
            owner="autonomy-runtime",
            current_stage=str(item["state"]),
        )
        for item in status["operations"]
    ]
    for incident in incidents:
        live_work.append(
            LiveWorkItem(
                work_id=incident.incident_id,
                title=incident.logical_lane_id,
                state=incident.disposition,
                owner="lane-registry",
                current_stage=incident.reason,
                blocked_by=(incident.logical_lane_id,)
                if incident.disposition == "HUMAN_REQUIRED"
                else (),
            )
        )
    human = [item for item in incidents if item.disposition == "HUMAN_REQUIRED"]
    health = HealthState.DEGRADED if human else HealthState.HEALTHY
    if status.get("pending_unknown_outcome"):
        health = HealthState.UNHEALTHY
    snapshot = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc-autonomy-runtime",
        project_id="PROJECT-PIPELINE",
        operating_mode="local-real",
        health=(
            HealthDimension(
                name="autonomy-runtime",
                state=health,
                reason="derived from durable supervisor, lane, provider, and service state",
            ),
        ),
        live_work=tuple(live_work),
        active_incident_ids=tuple(item.incident_id for item in human),
        provider_summary=provider_status
        or {"label": "unknown", "live_qualification": False, "source": "durable_state"},
        context_summary={
            "active_operation_id": status.get("active_operation_id"),
            "active_operation_state": status.get("active_operation_state"),
            "pending_unknown_outcome": status.get("pending_unknown_outcome"),
            "last_verified_sha": status.get("last_verified_sha"),
            "next_eligible_task_id": next_task,
            "windows_service": service_health or {"label": "absent"},
            "source": "durable_state",
        },
    )
    payload = snapshot.model_dump(mode="json")
    if payload.get("context_summary", {}).get("source") != "durable_state":
        raise RuntimeError("autonomy projection must derive from durable state")
    return payload
