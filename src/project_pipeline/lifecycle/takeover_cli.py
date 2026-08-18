"""Governed takeover writer CLI and control/scheduler governor projection."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.lifecycle.takeover import (
    AttestationState,
    DurableAttestation,
    DurableProviderQualificationEvidence,
    LaneState,
    ProviderQualificationState,
    SessionIdentity,
    _parse_utc_timestamp,
    global_stop_required,
    provider_dispatch_blocked,
    scoped_lane_state,
    validate_durable_attestation,
    validate_provider_qualification_evidence,
)


def takeover_policy(root: Path) -> dict[str, Any]:
    path = root / "config" / "cursor_takeover.json"
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def canonical_evidence_ref(root: Path, evidence_path: Path) -> str:
    try:
        return evidence_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(evidence_path.resolve())


def resolve_takeover_evidence(
    *,
    root: Path,
    evidence_ref: str,
    expected_project_id: str,
    expected_provider_id: str,
    expected_scope: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    reference = evidence_ref.strip()
    if not reference:
        return {
            "valid": False,
            "reasons": ["missing_evidence_reference"],
            "reference": evidence_ref,
            "canonical_ref": None,
            "resolved_path": None,
            "fingerprint": None,
            "payload": None,
        }
    candidate = Path(reference)
    evidence_path = candidate if candidate.is_absolute() else (root / candidate).resolve()
    resolved_path = str(evidence_path)
    if not evidence_path.is_file():
        reasons.append("missing_evidence_artifact")
        return {
            "valid": False,
            "reasons": reasons,
            "reference": evidence_ref,
            "canonical_ref": canonical_evidence_ref(root, evidence_path),
            "resolved_path": resolved_path,
            "fingerprint": None,
            "payload": None,
        }
    try:
        body = evidence_path.read_bytes()
    except OSError:
        reasons.append("unreadable_evidence_artifact")
        return {
            "valid": False,
            "reasons": reasons,
            "reference": evidence_ref,
            "canonical_ref": canonical_evidence_ref(root, evidence_path),
            "resolved_path": resolved_path,
            "fingerprint": None,
            "payload": None,
        }
    fingerprint = hashlib.sha256(body).hexdigest()
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        reasons.append("invalid_evidence_payload")
        payload = None
    if not isinstance(payload, dict):
        if "invalid_evidence_payload" not in reasons:
            reasons.append("invalid_evidence_payload")
        payload = None
    if isinstance(payload, dict) and (
        payload.get("project_id") != expected_project_id
        or payload.get("provider_id") != expected_provider_id
        or payload.get("scope") != expected_scope
    ):
        reasons.append("evidence_identity_mismatch")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "reference": evidence_ref,
        "canonical_ref": canonical_evidence_ref(root, evidence_path),
        "resolved_path": resolved_path,
        "fingerprint": fingerprint,
        "payload": payload,
    }


def takeover_attestation_path(root: Path) -> Path:
    override = Path(
        str(
            os.environ.get(
                "PROJECT_PIPELINE_TAKEOVER_ATTESTATION_PATH",
                root / ".local" / "state" / "takeover" / "privacy_attestation.json",
            )
        )
    )
    return override if override.is_absolute() else (root / override).resolve()


def takeover_provider_qualification_path(root: Path) -> Path:
    explicit_override = os.environ.get("PROJECT_PIPELINE_PROVIDER_QUALIFICATION_PATH")
    if explicit_override:
        override = Path(str(explicit_override))
    else:
        attestation_override = os.environ.get("PROJECT_PIPELINE_TAKEOVER_ATTESTATION_PATH")
        if attestation_override:
            override = Path(str(attestation_override)).with_name("provider_qualification.json")
        else:
            override = root / ".local" / "state" / "takeover" / "provider_qualification.json"
    return override if override.is_absolute() else (root / override).resolve()


def load_durable_attestation(root: Path) -> tuple[DurableAttestation | None, str]:
    path = takeover_attestation_path(root)
    if not path.is_file():
        return None, str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, str(path)
    if not isinstance(payload, dict):
        return None, str(path)
    fingerprint = payload.get("fingerprint")
    approved = payload.get("approved")
    if not isinstance(fingerprint, str) or not isinstance(approved, bool):
        return None, str(path)
    project_id = payload.get("project_id")
    provider_id = payload.get("provider_id")
    scope = payload.get("scope")
    approved_at_utc = payload.get("approved_at_utc")
    evidence_ref = payload.get("evidence_ref")
    evidence_fingerprint = payload.get("evidence_fingerprint")
    return (
        DurableAttestation(
            fingerprint=fingerprint,
            approved=approved,
            project_id=project_id if isinstance(project_id, str) else None,
            provider_id=provider_id if isinstance(provider_id, str) else None,
            scope=scope if isinstance(scope, str) else None,
            approved_at_utc=approved_at_utc if isinstance(approved_at_utc, str) else None,
            evidence_ref=evidence_ref if isinstance(evidence_ref, str) else None,
            evidence_fingerprint=(
                evidence_fingerprint if isinstance(evidence_fingerprint, str) else None
            ),
        ),
        str(path),
    )


def load_provider_qualification_evidence(
    root: Path,
) -> tuple[DurableProviderQualificationEvidence | None, str]:
    path = takeover_provider_qualification_path(root)
    if not path.is_file():
        return None, str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, str(path)
    if not isinstance(payload, dict):
        return None, str(path)
    qualified = payload.get("qualified")
    if not isinstance(qualified, bool):
        return None, str(path)
    fingerprint = payload.get("fingerprint")
    project_id = payload.get("project_id")
    provider_id = payload.get("provider_id")
    scope = payload.get("scope")
    verified_at_utc = payload.get("verified_at_utc")
    evidence_ref = payload.get("evidence_ref")
    evidence_fingerprint = payload.get("evidence_fingerprint")
    return (
        DurableProviderQualificationEvidence(
            qualified=qualified,
            fingerprint=fingerprint if isinstance(fingerprint, str) else None,
            project_id=project_id if isinstance(project_id, str) else None,
            provider_id=provider_id if isinstance(provider_id, str) else None,
            scope=scope if isinstance(scope, str) else None,
            verified_at_utc=verified_at_utc if isinstance(verified_at_utc, str) else None,
            evidence_ref=evidence_ref if isinstance(evidence_ref, str) else None,
            evidence_fingerprint=(
                evidence_fingerprint if isinstance(evidence_fingerprint, str) else None
            ),
        ),
        str(path),
    )


def takeover_evidence_reference_validation(
    *,
    root: Path,
    evidence_ref: str | None,
    evidence_fingerprint: str | None,
    expected_project_id: str,
    expected_provider_id: str,
    expected_scope: str,
    expected_timestamp_utc: str | None,
    max_age_hours: int | None,
    require_reference: bool,
    require_identity: bool,
    require_fingerprint: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    resolved_path: str | None = None
    actual_fingerprint: str | None = None
    fingerprint_matches = not require_fingerprint
    identity_matches = not require_identity
    fresh_within_policy = max_age_hours is None
    payload_is_json_object = False

    ref_value = evidence_ref.strip() if isinstance(evidence_ref, str) else ""
    if require_reference and not ref_value:
        reasons.append("missing_evidence_reference")
    evidence_path: Path | None = None
    if ref_value:
        candidate = Path(ref_value)
        evidence_path = candidate if candidate.is_absolute() else (root / candidate).resolve()
        resolved_path = str(evidence_path)
        if not evidence_path.is_file():
            reasons.append("missing_evidence_artifact")
            evidence_path = None

    evidence_payload: dict[str, Any] | None = None
    if evidence_path is not None:
        try:
            body = evidence_path.read_bytes()
        except OSError:
            reasons.append("unreadable_evidence_artifact")
            body = None
        if body is not None:
            actual_fingerprint = hashlib.sha256(body).hexdigest()
            if require_fingerprint:
                if not evidence_fingerprint:
                    reasons.append("missing_evidence_fingerprint")
                elif actual_fingerprint != evidence_fingerprint:
                    reasons.append("evidence_fingerprint_mismatch")
                else:
                    fingerprint_matches = True
            else:
                fingerprint_matches = True
            if require_identity or max_age_hours is not None:
                try:
                    loaded = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    reasons.append("invalid_evidence_payload")
                    loaded = None
                if isinstance(loaded, dict):
                    payload_is_json_object = True
                    evidence_payload = loaded

    if require_identity:
        if not payload_is_json_object or evidence_payload is None:
            reasons.append("missing_evidence_identity_fields")
        else:
            project_ok = evidence_payload.get("project_id") == expected_project_id
            provider_ok = evidence_payload.get("provider_id") == expected_provider_id
            scope_ok = evidence_payload.get("scope") == expected_scope
            identity_matches = project_ok and provider_ok and scope_ok
            if not identity_matches:
                reasons.append("evidence_identity_mismatch")

    if max_age_hours is not None:
        fresh_within_policy = False
        observed_timestamp = _parse_utc_timestamp(expected_timestamp_utc)
        if observed_timestamp is None:
            reasons.append("missing_evidence_timestamp")
        else:
            now_utc = datetime.now(UTC)
            age_hours = (now_utc - observed_timestamp).total_seconds() / 3600
            fresh_within_policy = 0 <= age_hours <= max_age_hours
            if not fresh_within_policy:
                reasons.append("evidence_stale")

    return {
        "valid": not reasons,
        "reference": evidence_ref,
        "resolved_path": resolved_path,
        "artifact_found": evidence_path is not None,
        "fingerprint_expected": evidence_fingerprint,
        "fingerprint_actual": actual_fingerprint,
        "fingerprint_matches": fingerprint_matches,
        "identity_matches": identity_matches,
        "fresh_within_policy": fresh_within_policy,
        "reasons": reasons,
    }


def attestation_state_from_reasons(reasons: tuple[str, ...] | list[str]) -> AttestationState:
    if any(reason.endswith("_stale") for reason in reasons):
        return AttestationState.STALE
    if any("mismatch" in reason for reason in reasons):
        return AttestationState.MISMATCHED
    if any(reason.startswith("missing_") for reason in reasons):
        return AttestationState.MISSING
    return AttestationState.INVALID


def provider_state_from_reasons(
    reasons: tuple[str, ...] | list[str],
) -> ProviderQualificationState:
    if any(reason.endswith("_stale") for reason in reasons):
        return ProviderQualificationState.STALE
    if any("mismatch" in reason for reason in reasons):
        return ProviderQualificationState.MISMATCHED
    if any(reason.startswith("missing_") for reason in reasons):
        return ProviderQualificationState.MISSING
    return ProviderQualificationState.INVALID


def write_takeover_record(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(serialized, encoding="utf-8", newline="\n")


def run_takeover_command(
    *,
    root: Path,
    action: str,
    project_id: str,
    provider_id: str,
    scope: str,
    evidence_ref: str,
) -> tuple[dict[str, Any], int]:
    evidence = resolve_takeover_evidence(
        root=root,
        evidence_ref=evidence_ref,
        expected_project_id=project_id,
        expected_provider_id=provider_id,
        expected_scope=scope,
    )
    if not evidence["valid"]:
        return {
            "ok": False,
            "action": action,
            "reasons": list(evidence["reasons"]),
            "evidence_reference": {
                "reference": evidence["reference"],
                "canonical_ref": evidence["canonical_ref"],
                "resolved_path": evidence["resolved_path"],
                "fingerprint": evidence["fingerprint"],
            },
        }, 1
    payload = evidence["payload"]
    assert isinstance(payload, dict)
    if action == "write-attestation":
        reasons: list[str] = []
        approved = payload.get("approved")
        if approved is not True:
            reasons.append("attestation_not_approved")
        approved_at_utc = payload.get("approved_at_utc")
        if not isinstance(approved_at_utc, str) or _parse_utc_timestamp(approved_at_utc) is None:
            reasons.append("missing_or_invalid_attestation_timestamp")
        if reasons:
            return {
                "ok": False,
                "action": action,
                "reasons": reasons,
                "evidence_reference": {
                    "reference": evidence["reference"],
                    "canonical_ref": evidence["canonical_ref"],
                    "resolved_path": evidence["resolved_path"],
                    "fingerprint": evidence["fingerprint"],
                },
            }, 1
        requires_privacy_attestation = bool(
            takeover_policy(root).get("require_privacy_mode", provider_id == "provider:cursor-cli")
        )
        fingerprint = DurableAttestation.fingerprint_for(
            {
                "project_id": project_id,
                "provider_id": provider_id,
                "scope": scope,
                "requires_privacy_attestation": requires_privacy_attestation,
            }
        )
        record = {
            "fingerprint": fingerprint,
            "approved": True,
            "project_id": project_id,
            "provider_id": provider_id,
            "scope": scope,
            "approved_at_utc": approved_at_utc,
            "evidence_ref": evidence["canonical_ref"],
            "evidence_fingerprint": evidence["fingerprint"],
        }
        path = takeover_attestation_path(root)
        write_takeover_record(path, record)
        return {"ok": True, "action": action, "path": str(path), "record": record}, 0
    reasons = []
    qualified = payload.get("qualified")
    if qualified is not True:
        reasons.append("provider_not_qualified")
    verified_at_utc = payload.get("verified_at_utc")
    if not isinstance(verified_at_utc, str) or _parse_utc_timestamp(verified_at_utc) is None:
        reasons.append("missing_or_invalid_provider_qualification_timestamp")
    if reasons:
        return {
            "ok": False,
            "action": action,
            "reasons": reasons,
            "evidence_reference": {
                "reference": evidence["reference"],
                "canonical_ref": evidence["canonical_ref"],
                "resolved_path": evidence["resolved_path"],
                "fingerprint": evidence["fingerprint"],
            },
        }, 1
    fingerprint = DurableProviderQualificationEvidence.fingerprint_for(
        project_id=project_id,
        provider_id=provider_id,
        scope=scope,
        qualified=True,
    )
    record = {
        "qualified": True,
        "fingerprint": fingerprint,
        "project_id": project_id,
        "provider_id": provider_id,
        "scope": scope,
        "verified_at_utc": verified_at_utc,
        "evidence_ref": evidence["canonical_ref"],
        "evidence_fingerprint": evidence["fingerprint"],
    }
    path = takeover_provider_qualification_path(root)
    write_takeover_record(path, record)
    return {"ok": True, "action": action, "path": str(path), "record": record}, 0


def takeover_governor_status(
    *,
    root: Path,
    project_id: str,
    provider_id: str,
    active_lane_count: int,
) -> dict[str, Any]:
    policy = takeover_policy(root)
    requires_privacy_attestation = bool(
        policy.get("require_privacy_mode", provider_id == "provider:cursor-cli")
    )
    require_attestation_identity = bool(policy.get("attestation_require_identity", True))
    require_attestation_evidence_reference = bool(
        policy.get("attestation_require_evidence_reference", True)
    )
    require_attestation_evidence_fingerprint = bool(
        policy.get("attestation_require_evidence_fingerprint", True)
    )
    max_attestation_age_hours = policy.get("attestation_max_age_hours")
    if not isinstance(max_attestation_age_hours, int) or max_attestation_age_hours <= 0:
        max_attestation_age_hours = None
    require_provider_qualification_identity = bool(
        policy.get("provider_qualification_require_identity", True)
    )
    require_provider_qualification_fingerprint = bool(
        policy.get("provider_qualification_require_fingerprint", True)
    )
    require_provider_qualification_evidence_reference = bool(
        policy.get("provider_qualification_require_evidence_reference", True)
    )
    require_provider_qualification_evidence_fingerprint = bool(
        policy.get("provider_qualification_require_evidence_fingerprint", True)
    )
    max_provider_qualification_age_hours = policy.get("provider_qualification_max_age_hours")
    if (
        not isinstance(max_provider_qualification_age_hours, int)
        or max_provider_qualification_age_hours <= 0
    ):
        max_provider_qualification_age_hours = None
    provider_scope = "local-governed-phase1"
    attestation_inputs = {
        "project_id": project_id,
        "provider_id": provider_id,
        "scope": provider_scope,
        "requires_privacy_attestation": requires_privacy_attestation,
    }
    prior_attestation, attestation_path = load_durable_attestation(root)
    prior_provider_qualification, provider_qualification_path = (
        load_provider_qualification_evidence(root)
    )
    attestation_validation = validate_durable_attestation(
        prior=prior_attestation,
        attestation_inputs=attestation_inputs,
        require_identity=require_attestation_identity,
        max_age_hours=max_attestation_age_hours,
    )
    provider_qualification_validation = validate_provider_qualification_evidence(
        evidence=prior_provider_qualification,
        project_id=project_id,
        provider_id=provider_id,
        scope=provider_scope,
        require_identity=require_provider_qualification_identity,
        require_fingerprint=require_provider_qualification_fingerprint,
        max_age_hours=max_provider_qualification_age_hours,
    )
    attestation_reference_validation = takeover_evidence_reference_validation(
        root=root,
        evidence_ref=None if prior_attestation is None else prior_attestation.evidence_ref,
        evidence_fingerprint=(
            None if prior_attestation is None else prior_attestation.evidence_fingerprint
        ),
        expected_project_id=project_id,
        expected_provider_id=provider_id,
        expected_scope=provider_scope,
        expected_timestamp_utc=None
        if prior_attestation is None
        else prior_attestation.approved_at_utc,
        max_age_hours=max_attestation_age_hours,
        require_reference=require_attestation_evidence_reference,
        require_identity=require_attestation_identity,
        require_fingerprint=require_attestation_evidence_fingerprint,
    )
    provider_reference_validation = takeover_evidence_reference_validation(
        root=root,
        evidence_ref=(
            None
            if prior_provider_qualification is None
            else prior_provider_qualification.evidence_ref
        ),
        evidence_fingerprint=(
            None
            if prior_provider_qualification is None
            else prior_provider_qualification.evidence_fingerprint
        ),
        expected_project_id=project_id,
        expected_provider_id=provider_id,
        expected_scope=provider_scope,
        expected_timestamp_utc=(
            None
            if prior_provider_qualification is None
            else prior_provider_qualification.verified_at_utc
        ),
        max_age_hours=max_provider_qualification_age_hours,
        require_reference=require_provider_qualification_evidence_reference,
        require_identity=require_provider_qualification_identity,
        require_fingerprint=require_provider_qualification_evidence_fingerprint,
    )
    attestation_gate_reasons = tuple(
        [*attestation_validation.reasons, *attestation_reference_validation["reasons"]]
    )
    attestation_gate_valid = (
        attestation_validation.valid and attestation_reference_validation["valid"]
    )
    attestation_gate_state = (
        AttestationState.VALID
        if attestation_gate_valid
        else attestation_state_from_reasons(attestation_gate_reasons)
    )
    provider_gate_reasons = tuple(
        [*provider_qualification_validation.reasons, *provider_reference_validation["reasons"]]
    )
    provider_qualification_satisfied = (
        provider_qualification_validation.satisfied and provider_reference_validation["valid"]
    )
    provider_qualification_state = (
        ProviderQualificationState.QUALIFIED
        if provider_qualification_satisfied
        else provider_state_from_reasons(provider_gate_reasons)
    )
    request_human_attestation = not attestation_gate_valid
    provider_lane_state = scoped_lane_state(
        has_privacy_attestation=attestation_gate_valid,
        requires_privacy_attestation=requires_privacy_attestation,
        missing_external_credentials=False,
        depends_on_external_credentials=False,
        resource_collision=False,
    )
    provider_gate_blocked = provider_dispatch_blocked(
        session_identity=SessionIdentity.PROGRAMMATIC_CURSOR_CLI_WORKER,
        provider_id=provider_id,
        provider_qualified=provider_qualification_satisfied,
    )
    provider_dispatch_eligible = (
        attestation_gate_valid and provider_qualification_satisfied and not provider_gate_blocked
    )
    local_lane_state = LaneState.ACTIVE if active_lane_count > 0 else LaneState.BLOCKED
    lane_matrix: list[dict[str, Any]] = [
        {
            "lane_id": "lane:local-governed",
            "state": local_lane_state.value,
            "eligible_unrelated_work_count": active_lane_count,
        },
        {
            "lane_id": f"lane:{provider_id}",
            "state": provider_lane_state.value,
            "requires_privacy_attestation": requires_privacy_attestation,
        },
    ]
    return {
        "attestation": {
            "source": "durable_local_state",
            "path": attestation_path,
            "found": prior_attestation is not None,
            "approved": None if prior_attestation is None else prior_attestation.approved,
            "request_human_attestation": request_human_attestation,
            "external_precondition": "BLOCKED_EXTERNAL" if request_human_attestation else None,
            "state": attestation_gate_state.value,
            "reasons": list(attestation_gate_reasons),
            "fingerprint_matches": attestation_validation.fingerprint_matches,
            "identity_matches": attestation_validation.identity_matches,
            "fresh_within_policy": attestation_validation.fresh_within_policy,
            "max_age_hours": max_attestation_age_hours,
            "expected_fingerprint": DurableAttestation.fingerprint_for(attestation_inputs),
            "evidence_reference": attestation_reference_validation,
        },
        "provider_dispatch": {
            "provider_id": provider_id,
            "provider_qualification_satisfied": provider_qualification_satisfied,
            "blocked_by_provider_gate": provider_gate_blocked,
            "eligible": provider_dispatch_eligible,
            "state": (
                ProviderQualificationState.QUALIFIED.value
                if provider_dispatch_eligible
                else provider_qualification_state.value
            ),
            "reasons": list(provider_gate_reasons),
            "qualification_evidence": {
                "source": "durable_local_state",
                "path": provider_qualification_path,
                "found": prior_provider_qualification is not None,
                "qualified": (
                    None
                    if prior_provider_qualification is None
                    else prior_provider_qualification.qualified
                ),
                "fingerprint_matches": provider_qualification_validation.fingerprint_matches,
                "identity_matches": provider_qualification_validation.identity_matches,
                "fresh_within_policy": provider_qualification_validation.fresh_within_policy,
                "max_age_hours": max_provider_qualification_age_hours,
                "evidence_ref": (
                    None
                    if prior_provider_qualification is None
                    else prior_provider_qualification.evidence_ref
                ),
                "evidence_fingerprint": (
                    None
                    if prior_provider_qualification is None
                    else prior_provider_qualification.evidence_fingerprint
                ),
                "reference_validation": provider_reference_validation,
            },
        },
        "gate_reconciliation": {
            "input_fingerprint": hashlib.sha256(
                json.dumps(
                    {
                        "project_id": project_id,
                        "provider_id": provider_id,
                        "scope": provider_scope,
                        "attestation": None
                        if prior_attestation is None
                        else {
                            "fingerprint": prior_attestation.fingerprint,
                            "approved": prior_attestation.approved,
                            "project_id": prior_attestation.project_id,
                            "provider_id": prior_attestation.provider_id,
                            "scope": prior_attestation.scope,
                            "approved_at_utc": prior_attestation.approved_at_utc,
                            "evidence_ref": prior_attestation.evidence_ref,
                            "evidence_fingerprint": prior_attestation.evidence_fingerprint,
                        },
                        "provider_qualification": None
                        if prior_provider_qualification is None
                        else {
                            "qualified": prior_provider_qualification.qualified,
                            "fingerprint": prior_provider_qualification.fingerprint,
                            "project_id": prior_provider_qualification.project_id,
                            "provider_id": prior_provider_qualification.provider_id,
                            "scope": prior_provider_qualification.scope,
                            "verified_at_utc": prior_provider_qualification.verified_at_utc,
                            "evidence_ref": prior_provider_qualification.evidence_ref,
                            "evidence_fingerprint": prior_provider_qualification.evidence_fingerprint,
                        },
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "attestation_gate": {
                "state": attestation_gate_state.value,
                "eligible": attestation_gate_valid,
                "reasons": list(attestation_gate_reasons),
            },
            "provider_qualification_gate": {
                "state": provider_qualification_state.value,
                "eligible": provider_qualification_satisfied,
                "reasons": list(provider_gate_reasons),
            },
        },
        "lane_matrix": lane_matrix,
        "global_stop_required": global_stop_required(
            tuple(LaneState(str(row["state"])) for row in lane_matrix)
        ),
    }
