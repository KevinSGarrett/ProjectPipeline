import pytest

from project_pipeline.command_center.agui import AGUIAdapter
from project_pipeline.command_center.models import HealthDimension, HealthState
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.contracts import EventEnvelope


def test_agui_run_requires_lifecycle_bookends():
    a = AGUIAdapter()
    events = (
        a.run_started(thread_id="thread:1", run_id="run:1"),
        *a.text_events("hello"),
        a.run_finished(thread_id="thread:1", run_id="run:1"),
    )
    a.validate_run(events)
    assert events[0]["type"] == "RUN_STARTED" and events[-1]["type"] == "RUN_FINISHED"


def test_agui_rejects_unterminated_run():
    a = AGUIAdapter()
    with pytest.raises(ValueError):
        a.validate_run((a.run_started(thread_id="thread:1", run_id="run:1"),))


def test_state_snapshot_remains_non_authoritative():
    snap = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:1",
        project_id="PROJ-TEST",
        operating_mode="NORMAL",
        health=(HealthDimension(name="control", state=HealthState.HEALTHY, reason="ok"),),
    )
    wire = AGUIAdapter.state_snapshot(snap)
    assert wire["type"] == "STATE_SNAPSHOT" and wire["snapshot"]["ui_state_authoritative"] is False


def test_internal_event_maps_to_custom_without_losing_identity():
    event = EventEnvelope(
        event_id="event:test:1",
        event_type="incident.opened",
        project_id="PROJ-TEST",
        producer="test",
        correlation_id="corr:test",
        aggregate_type="incident",
        aggregate_id="incident:1",
    )
    wire = AGUIAdapter.custom_event(event)
    assert (
        wire["type"] == "CUSTOM"
        and wire["name"] == "incident.opened"
        and wire["value"]["event_id"] == event.event_id
    )
