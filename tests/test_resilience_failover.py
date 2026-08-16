from datetime import UTC, datetime

from project_pipeline.domain.resilience import (
    FailureDomain,
    MachineHealth,
    MachineRole,
    OperatingMode,
)
from project_pipeline.resilience.failover import (
    RecoveryDirector,
    decide_operating_mode,
    verify_human_repair,
)


def m(mid, role, healthy, token):
    return MachineHealth(
        machine_id=mid,
        roles=(role,),
        healthy=healthy,
        heartbeat_at_utc=datetime.now(UTC),
        fencing_token=token,
    )


def test_failover_requires_fencing_and_witness():
    d = RecoveryDirector().decide_failover(
        m("control-a", MachineRole.PRIMARY_CONTROL, False, 4),
        m("control-b", MachineRole.STANDBY_CONTROL, True, 4),
        witness_confirmed=False,
        active_lease_expired=False,
    )
    assert not d.eligible and d.required_fencing_token == 5


def test_fenced_standby_takeover_is_eligible():
    d = RecoveryDirector().decide_failover(
        m("control-a", MachineRole.PRIMARY_CONTROL, False, 4),
        m("control-b", MachineRole.STANDBY_CONTROL, True, 4),
        witness_confirmed=True,
        active_lease_expired=True,
    )
    assert d.eligible and d.reconcile_before_commit


def test_cloud_outage_enters_local_first():
    d = decide_operating_mode((FailureDomain.CLOUD, FailureDomain.NETWORK))
    assert d.mode is OperatingMode.LOCAL_FIRST and "deterministic_control" in d.allowed_capabilities


def test_provider_substitution_preserves_task_semantics():
    r = RecoveryDirector.provider_substitution(
        ("reasoning",),
        (
            {"provider_id": "a", "available": False, "capabilities": ["reasoning"]},
            {"provider_id": "b", "available": True, "capabilities": ["reasoning"], "cost_score": 1},
        ),
    )
    assert r["selected_provider_id"] == "b" and r["task_semantics_preserved"]


def test_human_repair_is_verified_before_resume():
    bad = verify_human_repair(
        verification_results={"api": True, "state": False},
        stale_assumptions_invalidated=True,
        reconciliation_complete=True,
    )
    assert not bad["resume_eligible_work"]
    ok = verify_human_repair(
        verification_results={"api": True, "state": True},
        stale_assumptions_invalidated=True,
        reconciliation_complete=True,
    )
    assert ok["resume_eligible_work"]
