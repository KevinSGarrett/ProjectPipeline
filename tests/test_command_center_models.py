from project_pipeline.command_center.models import (
    HealthDimension,
    HealthState,
    LiveWorkItem,
    ReadinessMetric,
)
from project_pipeline.command_center.projections import CommandCenterProjectionService


def test_projection_preserves_non_authoritative_ui_boundary():
    svc = CommandCenterProjectionService()
    snap = svc.build_snapshot(
        snapshot_id="cc:test",
        project_id="PROJ-TEST",
        operating_mode="NORMAL",
        health=(
            HealthDimension(name="control", state=HealthState.HEALTHY, reason="heartbeat current"),
        ),
        completion_gate_state="NOT_COMPLETE",
        completion_percent=47.5,
        readiness=(
            ReadinessMetric(
                metric_id="r1", label="verification", value=0.4, basis="current evidence"
            ),
        ),
        live_work=(LiveWorkItem(work_id="work:1", title="Task", state="RUNNING"),),
    )
    assert snap.canonical_authority == "PROJECT_PIPELINE"
    assert snap.ui_state_authoritative is False
    assert snap.overall_health is HealthState.HEALTHY
    assert snap.completion_gate_state == "NOT_COMPLETE"
    assert len(snap.fingerprint) == 64


def test_unknown_or_stale_health_is_not_claimed_healthy():
    svc = CommandCenterProjectionService()
    assert svc.overall_health(()) is HealthState.UNKNOWN
    dims = (
        HealthDimension(name="control", state=HealthState.HEALTHY, reason="ok"),
        HealthDimension(name="provider", state=HealthState.UNKNOWN, reason="no observation"),
    )
    assert svc.overall_health(dims) is HealthState.UNKNOWN


def test_unhealthy_known_dimension_survives_other_unknown_dimension():
    svc = CommandCenterProjectionService()
    dims = (
        HealthDimension(name="control", state=HealthState.UNHEALTHY, reason="failed"),
        HealthDimension(name="provider", state=HealthState.UNKNOWN, reason="no observation"),
    )
    assert svc.overall_health(dims) is HealthState.UNHEALTHY
