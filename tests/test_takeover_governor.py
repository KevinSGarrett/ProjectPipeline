from __future__ import annotations

from project_pipeline.lifecycle import (
    CheckpointDecision,
    DurableAttestation,
    LaneState,
    ReadinessEvidence,
    SessionIdentity,
    attestation_recheck_required,
    claim_is_admissible,
    global_stop_required,
    local_integration_allowed,
    pp327_collision,
    provider_dispatch_blocked,
    scoped_lane_state,
)


def test_autonomy_coordinator_can_integrate_a_qualified_provider() -> None:
    assert local_integration_allowed(
        session_identity=SessionIdentity.AUTONOMY_COORDINATOR,
        provider_id="provider:local",
        provider_qualified=True,
    )


def test_missing_provider_qualification_blocks_every_dispatch_identity() -> None:
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


def test_missing_privacy_attestation_creates_scoped_external_block_only() -> None:
    assert (
        scoped_lane_state(
            has_privacy_attestation=False,
            requires_privacy_attestation=True,
            missing_external_credentials=False,
            depends_on_external_credentials=False,
            resource_collision=False,
        )
        is LaneState.BLOCKED_EXTERNAL
    )
    assert (
        scoped_lane_state(
            has_privacy_attestation=False,
            requires_privacy_attestation=False,
            missing_external_credentials=False,
            depends_on_external_credentials=False,
            resource_collision=False,
        )
        is LaneState.ACTIVE
    )


def test_valid_durable_attestation_is_reused_until_fingerprint_changes() -> None:
    inputs = {"privacy_mode": "strict", "policy_version": "v1"}
    fingerprint = DurableAttestation.fingerprint_for(inputs)
    prior = DurableAttestation(fingerprint=fingerprint, approved=True)
    assert not attestation_recheck_required(prior=prior, attestation_inputs=inputs)
    assert attestation_recheck_required(
        prior=prior, attestation_inputs={"privacy_mode": "strict", "policy_version": "v2"}
    )


def test_pp327_collision_is_scoped_to_exact_owned_paths() -> None:
    assert pp327_collision(("src/project_pipeline/domain/state.py",))
    assert not pp327_collision(("src/project_pipeline/lifecycle/takeover.py",))


def test_non_overlapping_pp379_pp380_claims_remain_admissible() -> None:
    assert claim_is_admissible(
        ("src/project_pipeline/lifecycle/takeover.py", "tests/test_takeover_governor.py")
    )


def test_checkpoint_is_invalid_when_eligible_unrelated_lane_exists() -> None:
    assert not CheckpointDecision(
        no_additional_action_needed=True, eligible_unrelated_lanes=("lane:local-governed",)
    ).is_valid()
    assert CheckpointDecision(
        no_additional_action_needed=False, eligible_unrelated_lanes=("lane:local-governed",)
    ).is_valid()


def test_activation_ready_flips_true_when_evidence_is_satisfied() -> None:
    evidence = ReadinessEvidence(
        exec_available=True,
        auth_non_secret=True,
        privacy_attested=True,
        representative_qualified=True,
        rollback_verified=True,
        external_write_isolated=True,
        freshness_satisfied=True,
        unattended_qualification_satisfied=False,
    )
    assert evidence.activation_ready


def test_unattended_ready_is_evidence_derived() -> None:
    evidence = ReadinessEvidence(
        exec_available=True,
        auth_non_secret=True,
        privacy_attested=True,
        representative_qualified=True,
        rollback_verified=True,
        external_write_isolated=True,
        freshness_satisfied=True,
        unattended_qualification_satisfied=False,
    )
    assert not evidence.unattended_ready
    promoted = ReadinessEvidence(
        **{**evidence.__dict__, "unattended_qualification_satisfied": True}
    )
    assert promoted.unattended_ready


def test_repeated_sessions_reuse_unchanged_attestation() -> None:
    inputs = {"privacy_mode": "strict", "scope": "local-governed-phase1"}
    prior = DurableAttestation(
        fingerprint=DurableAttestation.fingerprint_for(inputs),
        approved=True,
    )
    assert not attestation_recheck_required(prior=prior, attestation_inputs=inputs)


def test_global_stop_only_when_all_safe_lanes_blocked() -> None:
    assert not global_stop_required((LaneState.ACTIVE, LaneState.BLOCKED_EXTERNAL))
    assert global_stop_required((LaneState.BLOCKED, LaneState.BLOCKED_EXTERNAL))
