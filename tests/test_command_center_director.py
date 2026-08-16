import pytest

from project_pipeline.command_center.director import (
    CommandCenterControlGateway,
    DirectorContextBuilder,
)
from project_pipeline.command_center.models import CommandCenterScope, HealthDimension, HealthState
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.contracts import (
    ActionIntent,
    ApprovalState,
    CommandEnvelope,
    CommandResult,
    CommandStatus,
)
from project_pipeline.core.command_bus import CommandProcessor
from project_pipeline.core.journal import LocalCommandJournal


def command(with_intent=True):
    kwargs = dict(
        command_id="command:test:1",
        command_type="control.pause",
        project_id="PROJ-TEST",
        actor_id="actor:test",
        correlation_id="corr:test",
        idempotency_key="idem-test-0001",
        payload={},
    )
    if with_intent:
        kwargs["action_intent"] = ActionIntent(
            action_id="action:test:1",
            actor_id="actor:test",
            authority="operator",
            target="PROJ-TEST",
            operation="control.pause",
            idempotency_key="idem-test-0001",
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:test",
        )
    return CommandEnvelope(**kwargs)


def processor(tmp_path):
    p = CommandProcessor(LocalCommandJournal(tmp_path / "journal"))

    def h(c):
        return CommandResult(
            command_id=c.command_id,
            command_type=c.command_type,
            project_id=c.project_id,
            correlation_id=c.correlation_id,
            idempotency_key=c.idempotency_key,
            status=CommandStatus.SUCCEEDED,
            output={"paused": True},
        )

    p.register("control.pause", h)
    return p


def test_control_gateway_requires_typed_action_intent(tmp_path):
    g = CommandCenterControlGateway(processor(tmp_path), lambda c: True)
    with pytest.raises(PermissionError):
        g.execute(command(False))


def test_control_gateway_obeys_authorization(tmp_path):
    g = CommandCenterControlGateway(processor(tmp_path), lambda c: False)
    with pytest.raises(PermissionError):
        g.execute(command())


def test_control_gateway_uses_normal_idempotent_command_processor(tmp_path):
    g = CommandCenterControlGateway(processor(tmp_path), lambda c: True)
    first = g.execute(command())
    second = g.execute(command())
    assert first.status is CommandStatus.SUCCEEDED and second.replayed is True


def test_director_context_scrubs_private_reasoning_keys():
    snap = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:1",
        project_id="PROJ-TEST",
        operating_mode="NORMAL",
        health=(HealthDimension(name="control", state=HealthState.HEALTHY, reason="ok"),),
        context_summary={"private_reasoning": "secret", "public": "fact"},
    )
    ctx = DirectorContextBuilder().build(
        snap, scope=CommandCenterScope.PROJECT, source_ids=("live",)
    )
    assert (
        ctx.private_reasoning_exposed is False
        and "private_reasoning" not in str(ctx.facts)
        and "public" in str(ctx.facts)
    )


def test_incident_context_requires_incident_id():
    snap = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:1", project_id="PROJ-TEST", operating_mode="NORMAL", health=()
    )
    with pytest.raises(ValueError):
        DirectorContextBuilder().build(snap, scope=CommandCenterScope.INCIDENT)
