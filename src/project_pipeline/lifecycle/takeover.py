from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

CANONICAL_PURSUING_GOAL = (
    "Deliver and qualify ProjectPipeline as a continuously operating, local-first "
    "autonomous engineering organization that accepts complete project inputs, "
    "compiles a verified project model, autonomously selects and executes genuinely "
    "missing work through conflict-safe parallel lanes and qualified workers, verifies "
    "results, governs GitHub and Jira, merges accepted changes, reconciles external "
    "state, recomputes project state, handles HUMAN_REQUIRED incidents without stopping "
    "unaffected work, exposes truthful live state through the Command Center, and "
    "continues until the deterministic Completion Gate reports COMPLETE for the "
    "integrated, released, and operationally verified system."
)

CANONICAL_SOURCE_REFERENCES = ("SRC-014:L000001-L000087", "SRC-015:L000031-L000150")

PP327_BLOCKED_PATHS = frozenset(
    {
        "jira/tasks/PP-TASK-000327.json",
        "src/project_pipeline/domain/state.py",
        "src/project_pipeline/jira_steward/reconciliation.py",
        "tests/test_domain_models.py",
        "tests/test_jira_steward_domain.py",
    }
)


class SessionIdentity(StrEnum):
    OPERATOR_LAUNCHED_COORDINATOR = "OPERATOR_LAUNCHED_COORDINATOR"
    PROGRAMMATIC_CURSOR_CLI_WORKER = "PROGRAMMATIC_CURSOR_CLI_WORKER"
    CURSOR_CLOUD_WORKER = "CURSOR_CLOUD_WORKER"


class LaneState(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


@dataclass(frozen=True)
class ReadinessEvidence:
    exec_available: bool
    auth_non_secret: bool
    privacy_attested: bool
    representative_qualified: bool
    rollback_verified: bool
    external_write_isolated: bool
    freshness_satisfied: bool
    unattended_qualification_satisfied: bool

    @property
    def activation_ready(self) -> bool:
        return all(
            (
                self.exec_available,
                self.auth_non_secret,
                self.privacy_attested,
                self.representative_qualified,
                self.rollback_verified,
                self.external_write_isolated,
                self.freshness_satisfied,
            )
        )

    @property
    def unattended_ready(self) -> bool:
        return self.activation_ready and self.unattended_qualification_satisfied


@dataclass(frozen=True)
class DurableAttestation:
    fingerprint: str
    approved: bool

    @staticmethod
    def fingerprint_for(value: dict[str, object]) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CheckpointDecision:
    no_additional_action_needed: bool
    eligible_unrelated_lanes: tuple[str, ...]

    def is_valid(self) -> bool:
        return not (self.no_additional_action_needed and bool(self.eligible_unrelated_lanes))


def has_path_collision(left_paths: tuple[str, ...], right_paths: tuple[str, ...]) -> bool:
    left = {item.replace("\\", "/").strip("/") for item in left_paths}
    right = {item.replace("\\", "/").strip("/") for item in right_paths}
    return bool(left & right)


def pp327_collision(paths: tuple[str, ...]) -> bool:
    normalized = {item.replace("\\", "/").strip("/") for item in paths}
    return bool(normalized & PP327_BLOCKED_PATHS)


def claim_is_admissible(paths: tuple[str, ...]) -> bool:
    return not pp327_collision(paths)


def provider_dispatch_blocked(
    *,
    session_identity: SessionIdentity,
    provider_id: str,
    provider_qualified: bool,
) -> bool:
    if provider_qualified:
        return False
    if provider_id != "provider:cursor-cli":
        return True
    return session_identity is SessionIdentity.PROGRAMMATIC_CURSOR_CLI_WORKER


def local_integration_allowed(
    *,
    session_identity: SessionIdentity,
    provider_id: str,
    provider_qualified: bool,
) -> bool:
    if provider_dispatch_blocked(
        session_identity=session_identity,
        provider_id=provider_id,
        provider_qualified=provider_qualified,
    ):
        return False
    return session_identity is SessionIdentity.OPERATOR_LAUNCHED_COORDINATOR


def scoped_lane_state(
    *,
    has_privacy_attestation: bool,
    requires_privacy_attestation: bool,
    missing_external_credentials: bool,
    depends_on_external_credentials: bool,
    resource_collision: bool,
) -> LaneState:
    if resource_collision:
        return LaneState.BLOCKED
    if missing_external_credentials and depends_on_external_credentials:
        return LaneState.BLOCKED
    if requires_privacy_attestation and not has_privacy_attestation:
        return LaneState.HUMAN_REQUIRED
    return LaneState.ACTIVE


def global_stop_required(lane_states: tuple[LaneState, ...]) -> bool:
    if not lane_states:
        return True
    return all(state in {LaneState.BLOCKED, LaneState.HUMAN_REQUIRED} for state in lane_states)


def should_request_human_attestation(
    *,
    prior: DurableAttestation | None,
    attestation_inputs: dict[str, object],
) -> bool:
    fingerprint = DurableAttestation.fingerprint_for(attestation_inputs)
    if prior is None:
        return True
    if not prior.approved:
        return True
    return prior.fingerprint != fingerprint
