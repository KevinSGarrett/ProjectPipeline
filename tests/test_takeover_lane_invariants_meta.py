from __future__ import annotations

from project_pipeline.lifecycle.takeover import (
    DurableAttestation,
    LaneState,
    SessionIdentity,
    attestation_recheck_required,
    claim_is_admissible,
    global_stop_required,
    has_path_collision,
    local_integration_allowed,
    pp327_collision,
    provider_dispatch_blocked,
    scoped_lane_state,
)


def test_scoped_blocker_behavior_does_not_force_global_stop() -> None:
    blocked = scoped_lane_state(
        has_privacy_attestation=True,
        requires_privacy_attestation=False,
        missing_external_credentials=True,
        depends_on_external_credentials=True,
        resource_collision=False,
    )
    active = scoped_lane_state(
        has_privacy_attestation=False,
        requires_privacy_attestation=False,
        missing_external_credentials=False,
        depends_on_external_credentials=False,
        resource_collision=False,
    )
    assert blocked is LaneState.BLOCKED
    assert active is LaneState.ACTIVE
    assert not global_stop_required((blocked, active))


def test_continuation_enforcement_reuses_attestation_fingerprint() -> None:
    baseline = {"privacy_mode": "strict", "lane_scope": "provider:local"}
    prior = DurableAttestation(
        fingerprint=DurableAttestation.fingerprint_for(baseline),
        approved=True,
    )
    assert not attestation_recheck_required(prior=prior, attestation_inputs=baseline)
    assert attestation_recheck_required(
        prior=prior,
        attestation_inputs={**baseline, "lane_scope": "provider:cursor-cli"},
    )


def test_provider_lane_isolation_requires_qualification_for_every_identity() -> None:
    assert provider_dispatch_blocked(
        session_identity=SessionIdentity.PROGRAMMATIC_CURSOR_CLI_WORKER,
        provider_id="provider:cursor-cli",
        provider_qualified=False,
    )
    assert provider_dispatch_blocked(
        session_identity=SessionIdentity.AUTONOMY_COORDINATOR,
        provider_id="provider:cursor-cli",
        provider_qualified=False,
    )
    assert local_integration_allowed(
        session_identity=SessionIdentity.AUTONOMY_COORDINATOR,
        provider_id="provider:local",
        provider_qualified=True,
    )


def test_non_overlapping_claims_remain_admissible() -> None:
    lane_a = ("src/project_pipeline/lifecycle/takeover.py",)
    lane_b = ("tests/test_takeover_lane_invariants_meta.py",)
    assert not has_path_collision(lane_a, lane_b)
    assert claim_is_admissible(lane_a + lane_b)
    assert not claim_is_admissible(("src/project_pipeline/domain/state.py",))
    assert pp327_collision(("src/project_pipeline/domain/state.py",))
