from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json


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


class AttestationState(StrEnum):
    MISSING = "MISSING"
    INVALID = "INVALID"
    MISMATCHED = "MISMATCHED"
    STALE = "STALE"
    VALID = "VALID"


class ProviderQualificationState(StrEnum):
    MISSING = "MISSING"
    INVALID = "INVALID"
    MISMATCHED = "MISMATCHED"
    STALE = "STALE"
    QUALIFIED = "QUALIFIED"


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
    project_id: str | None = None
    provider_id: str | None = None
    scope: str | None = None
    approved_at_utc: str | None = None
    evidence_ref: str | None = None
    evidence_fingerprint: str | None = None

    @staticmethod
    def fingerprint_for(value: dict[str, object]) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AttestationValidation:
    valid: bool
    state: AttestationState
    reasons: tuple[str, ...]
    fingerprint_matches: bool
    identity_matches: bool
    fresh_within_policy: bool


@dataclass(frozen=True)
class DurableProviderQualificationEvidence:
    qualified: bool
    fingerprint: str | None = None
    project_id: str | None = None
    provider_id: str | None = None
    scope: str | None = None
    verified_at_utc: str | None = None
    evidence_ref: str | None = None
    evidence_fingerprint: str | None = None

    @staticmethod
    def fingerprint_for(
        *,
        project_id: str,
        provider_id: str,
        scope: str,
        qualified: bool,
    ) -> str:
        payload = {
            "project_id": project_id,
            "provider_id": provider_id,
            "scope": scope,
            "qualified": qualified,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderQualificationValidation:
    satisfied: bool
    state: ProviderQualificationState
    reasons: tuple[str, ...]
    fingerprint_matches: bool
    identity_matches: bool
    fresh_within_policy: bool


@dataclass(frozen=True)
class CheckpointDecision:
    no_additional_action_needed: bool
    eligible_unrelated_lanes: tuple[str, ...]

    def is_valid(self) -> bool:
        return not (
            self.no_additional_action_needed and bool(self.eligible_unrelated_lanes)
        )


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


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def validate_durable_attestation(
    *,
    prior: DurableAttestation | None,
    attestation_inputs: dict[str, object],
    require_identity: bool,
    max_age_hours: int | None,
    now: datetime | None = None,
) -> AttestationValidation:
    expected_fingerprint = DurableAttestation.fingerprint_for(attestation_inputs)
    if prior is None:
        return AttestationValidation(
            valid=False,
            state=AttestationState.MISSING,
            reasons=("missing_durable_attestation",),
            fingerprint_matches=False,
            identity_matches=False,
            fresh_within_policy=False,
        )
    if not prior.approved:
        return AttestationValidation(
            valid=False,
            state=AttestationState.INVALID,
            reasons=("attestation_not_approved",),
            fingerprint_matches=False,
            identity_matches=False,
            fresh_within_policy=False,
        )
    fingerprint_matches = prior.fingerprint == expected_fingerprint
    if not fingerprint_matches:
        return AttestationValidation(
            valid=False,
            state=AttestationState.MISMATCHED,
            reasons=("fingerprint_mismatch",),
            fingerprint_matches=False,
            identity_matches=False,
            fresh_within_policy=False,
        )
    identity_matches = True
    if require_identity:
        expected_project_id = str(attestation_inputs.get("project_id", ""))
        expected_provider_id = str(attestation_inputs.get("provider_id", ""))
        expected_scope = str(attestation_inputs.get("scope", ""))
        identity_matches = (
            prior.project_id == expected_project_id
            and prior.provider_id == expected_provider_id
            and prior.scope == expected_scope
        )
        if not identity_matches:
            return AttestationValidation(
                valid=False,
                state=AttestationState.MISMATCHED,
                reasons=("identity_mismatch",),
                fingerprint_matches=True,
                identity_matches=False,
                fresh_within_policy=False,
            )
    fresh_within_policy = True
    if max_age_hours is not None:
        issued_at = _parse_utc_timestamp(prior.approved_at_utc)
        if issued_at is None:
            return AttestationValidation(
                valid=False,
                state=AttestationState.STALE,
                reasons=("missing_or_invalid_timestamp",),
                fingerprint_matches=True,
                identity_matches=identity_matches,
                fresh_within_policy=False,
            )
        evaluated_at = (now or datetime.now(UTC)).astimezone(UTC)
        age_hours = (evaluated_at - issued_at).total_seconds() / 3600
        fresh_within_policy = 0 <= age_hours <= max_age_hours
        if not fresh_within_policy:
            return AttestationValidation(
                valid=False,
                state=AttestationState.STALE,
                reasons=("attestation_stale",),
                fingerprint_matches=True,
                identity_matches=identity_matches,
                fresh_within_policy=False,
            )
    return AttestationValidation(
        valid=True,
        state=AttestationState.VALID,
        reasons=(),
        fingerprint_matches=True,
        identity_matches=identity_matches,
        fresh_within_policy=fresh_within_policy,
    )


def should_request_human_attestation(
    *,
    prior: DurableAttestation | None,
    attestation_inputs: dict[str, object],
) -> bool:
    validation = validate_durable_attestation(
        prior=prior,
        attestation_inputs=attestation_inputs,
        require_identity=False,
        max_age_hours=None,
    )
    return not validation.valid


def validate_provider_qualification_evidence(
    *,
    evidence: DurableProviderQualificationEvidence | None,
    project_id: str,
    provider_id: str,
    scope: str,
    require_identity: bool,
    require_fingerprint: bool,
    max_age_hours: int | None,
    now: datetime | None = None,
) -> ProviderQualificationValidation:
    expected_fingerprint = DurableProviderQualificationEvidence.fingerprint_for(
        project_id=project_id,
        provider_id=provider_id,
        scope=scope,
        qualified=True,
    )
    if evidence is None:
        return ProviderQualificationValidation(
            satisfied=False,
            state=ProviderQualificationState.MISSING,
            reasons=("missing_provider_qualification_evidence",),
            fingerprint_matches=False,
            identity_matches=False,
            fresh_within_policy=False,
        )
    if not evidence.qualified:
        return ProviderQualificationValidation(
            satisfied=False,
            state=ProviderQualificationState.INVALID,
            reasons=("provider_not_qualified",),
            fingerprint_matches=False,
            identity_matches=False,
            fresh_within_policy=False,
        )
    fingerprint_matches = True
    if require_fingerprint:
        if not evidence.fingerprint:
            return ProviderQualificationValidation(
                satisfied=False,
                state=ProviderQualificationState.INVALID,
                reasons=("missing_provider_qualification_fingerprint",),
                fingerprint_matches=False,
                identity_matches=False,
                fresh_within_policy=False,
            )
        fingerprint_matches = evidence.fingerprint == expected_fingerprint
        if not fingerprint_matches:
            return ProviderQualificationValidation(
                satisfied=False,
                state=ProviderQualificationState.MISMATCHED,
                reasons=("provider_qualification_fingerprint_mismatch",),
                fingerprint_matches=False,
                identity_matches=False,
                fresh_within_policy=False,
            )
    identity_matches = True
    if require_identity:
        identity_matches = (
            evidence.project_id == project_id
            and evidence.provider_id == provider_id
            and evidence.scope == scope
        )
        if not identity_matches:
            return ProviderQualificationValidation(
                satisfied=False,
                state=ProviderQualificationState.MISMATCHED,
                reasons=("provider_qualification_identity_mismatch",),
                fingerprint_matches=fingerprint_matches,
                identity_matches=False,
                fresh_within_policy=False,
            )
    fresh_within_policy = True
    if max_age_hours is not None:
        verified_at = _parse_utc_timestamp(evidence.verified_at_utc)
        if verified_at is None:
            return ProviderQualificationValidation(
                satisfied=False,
                state=ProviderQualificationState.STALE,
                reasons=("missing_or_invalid_provider_qualification_timestamp",),
                fingerprint_matches=fingerprint_matches,
                identity_matches=identity_matches,
                fresh_within_policy=False,
            )
        evaluated_at = (now or datetime.now(UTC)).astimezone(UTC)
        age_hours = (evaluated_at - verified_at).total_seconds() / 3600
        fresh_within_policy = 0 <= age_hours <= max_age_hours
        if not fresh_within_policy:
            return ProviderQualificationValidation(
                satisfied=False,
                state=ProviderQualificationState.STALE,
                reasons=("provider_qualification_stale",),
                    fingerprint_matches=fingerprint_matches,
                identity_matches=identity_matches,
                fresh_within_policy=False,
            )
    return ProviderQualificationValidation(
        satisfied=True,
        state=ProviderQualificationState.QUALIFIED,
        reasons=(),
        fingerprint_matches=fingerprint_matches,
        identity_matches=identity_matches,
        fresh_within_policy=fresh_within_policy,
    )
