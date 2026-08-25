"""Idempotent recovery and current-policy validation of PP-379 attestation artifacts.

This module never converts an invalid artifact into a valid one by copying it.
Restored public bytes must match the preserved digest exactly. Durable private
records are read for provenance and validator input; they are not rewritten here.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from project_pipeline.lifecycle.takeover import (
    DurableAttestation,
    DurableProviderQualificationEvidence,
    validate_durable_attestation,
    validate_provider_qualification_evidence,
)

PROJECT_ID = "PROJECT-PIPELINE"
PROVIDER_ID = "provider:cursor-cli"
SCOPE = "local-governed-phase1"

PUBLIC_ATTESTATION_REF = "evidence/pp379_writer_attestation_evidence.json"
PUBLIC_QUALIFICATION_REF = "evidence/pp379_writer_provider_qualification_evidence.json"
HISTORICAL_RECEIPT_REF = "evidence/control_completion_post_remediation.json"
PROVENANCE_REF = "evidence/pp379_attestation_recovery_provenance.json"

EXPECTED_PUBLIC_ATTESTATION_SHA256 = (
    "b47d6d76d6eb7221e1d5d074f22b3793714ca120487314dd3816394f3745c32f"
)
EXPECTED_PUBLIC_QUALIFICATION_SHA256 = (
    "99b41e93da8c59d111a77ddd02784da1904cbfaa95c99cb95d4b0573cc0ae00a"
)
EXPECTED_PUBLIC_ATTESTATION_BYTES = 185
EXPECTED_PUBLIC_QUALIFICATION_BYTES = 186
HISTORICAL_ATTESTATION_FINGERPRINT = (
    "a21027dbe356826f49b350e6bc9ec6d5c4cd5d00a0e440d6995313dc61942b89"
)

DEFAULT_PRESERVATION_ROOT = Path(r"C:\Project_X\.local\pm_cycle_010\preservation\canonical-main")
DEFAULT_DURABLE_DIR = Path(r"C:\Project_X\.local\state\takeover")


def resolve_durable_dir(repository_root: Path, durable_dir: Path | None = None) -> Path:
    """Prefer an explicit dir, then machine-local private records, then repo-relative state."""
    if durable_dir is not None:
        return durable_dir
    if (DEFAULT_DURABLE_DIR / "privacy_attestation.json").is_file() and (
        DEFAULT_DURABLE_DIR / "provider_qualification.json"
    ).is_file():
        return DEFAULT_DURABLE_DIR
    return repository_root / ".local" / "state" / "takeover"


class RecoveryDisposition(StrEnum):
    RECOVERED_VALID = "RECOVERED_VALID"
    RECOVERED_BUT_STALE = "RECOVERED_BUT_STALE"
    REQUALIFIED_VALID = "REQUALIFIED_VALID"
    MISMATCHED = "MISMATCHED"
    MISSING = "MISSING"


class RecoveryError(ValueError):
    """Raised when an import would write mismatched or unauthorized bytes."""


def _parse_public_record(
    path: Path, *, expected_sha256: str, expected_bytes: int
) -> dict[str, Any]:
    if not path.is_file():
        raise RecoveryError(f"required public record is missing: {path}")
    payload = path.read_bytes()
    if len(payload) != expected_bytes or sha256_bytes(payload) != expected_sha256:
        raise RecoveryError("public record digest or length does not match the accepted subject")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryError("public record is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise RecoveryError("public record is not a JSON object")
    return parsed


def _require_utc_timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecoveryError(f"public record has no valid {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RecoveryError(f"public record has no valid {field}") from error
    if parsed.tzinfo is None:
        raise RecoveryError(f"public record has no valid {field}")
    return value


def _write_local_record_once(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Create one local record without ever overwriting an existing record."""
    encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        return {"path": str(path), "applied": False, "reason": "already-present"}
    actual = path.read_bytes()
    if actual != encoded:
        raise RecoveryError("machine-local attestation readback did not match the requested record")
    return {
        "path": str(path),
        "applied": True,
        "sha256": sha256_bytes(actual),
        "byte_length": len(actual),
    }


def _resolve_bootstrap_durable_dir(repository_root: Path, durable_dir: Path | None) -> Path:
    """Return a worker-local destination for newly derived private records.

    ``resolve_durable_dir`` deliberately supports legacy recovery flows that may
    use the canonical coordinator state.  A new isolated-worker bootstrap has a
    stricter ownership boundary: both its default and any explicit destination
    must live under this clone's ``.local`` directory.
    """
    local_root = (repository_root / ".local").resolve()
    target = (durable_dir or local_root / "state" / "takeover").resolve()
    try:
        target.relative_to(local_root)
    except ValueError as error:
        raise RecoveryError(
            "machine-local bootstrap durable_dir must be within repository_root/.local"
        ) from error
    return target


def bootstrap_machine_local_attestation_records(
    *,
    repository_root: Path,
    durable_dir: Path | None = None,
    verification_dir: Path | None = None,
) -> dict[str, Any]:
    """Establish CPU-local attestation records from accepted public evidence.

    This is deliberately a one-way, no-overwrite bootstrap for a newly isolated
    worker. It never imports a different machine's private state, credential, or
    campaign evidence. Exact public bytes and the active policy must validate
    before any local record is created, and the result is independently
    re-evaluated before it is returned.
    """
    repository_root = repository_root.resolve()
    target = _resolve_bootstrap_durable_dir(repository_root, durable_dir)
    verify = (verification_dir or target / "bootstrap-verification").resolve()
    policy = load_current_attestation_policy(repository_root)
    public_attestation = _parse_public_record(
        repository_root / PUBLIC_ATTESTATION_REF,
        expected_sha256=EXPECTED_PUBLIC_ATTESTATION_SHA256,
        expected_bytes=EXPECTED_PUBLIC_ATTESTATION_BYTES,
    )
    public_qualification = _parse_public_record(
        repository_root / PUBLIC_QUALIFICATION_REF,
        expected_sha256=EXPECTED_PUBLIC_QUALIFICATION_SHA256,
        expected_bytes=EXPECTED_PUBLIC_QUALIFICATION_BYTES,
    )
    required_identity = {
        "project_id": policy.project_id,
        "provider_id": policy.provider_id,
        "scope": policy.scope,
    }
    if (
        any(public_attestation.get(key) != value for key, value in required_identity.items())
        or public_attestation.get("approved") is not True
        or any(public_qualification.get(key) != value for key, value in required_identity.items())
        or public_qualification.get("qualified") is not True
    ):
        raise RecoveryError("public records do not match the active attestation policy")
    approved_at = _require_utc_timestamp(
        public_attestation.get("approved_at_utc"), field="approved_at_utc"
    )
    verified_at = _require_utc_timestamp(
        public_qualification.get("verified_at_utc"), field="verified_at_utc"
    )
    attestation_fingerprint = DurableAttestation.fingerprint_for(policy.attestation_inputs())
    if attestation_fingerprint != HISTORICAL_ATTESTATION_FINGERPRINT:
        raise RecoveryError("active policy does not match the accepted attestation fingerprint")
    qualification_fingerprint = DurableProviderQualificationEvidence.fingerprint_for(
        project_id=policy.project_id,
        provider_id=policy.provider_id,
        scope=policy.scope,
        qualified=True,
    )
    preexisting = evaluate_attestation_recovery(
        repository_root=repository_root,
        source_attestation=repository_root / PUBLIC_ATTESTATION_REF,
        source_qualification=repository_root / PUBLIC_QUALIFICATION_REF,
        durable_attestation_path=target / "privacy_attestation.json",
        durable_qualification_path=target / "provider_qualification.json",
        verification_dir=verify / "before-bootstrap",
        historical_receipt_path=repository_root / HISTORICAL_RECEIPT_REF,
        policy=policy,
    )
    preexisting_by_kind = {item["kind"]: item for item in preexisting["artifacts"]}
    for filename, kind in (
        ("privacy_attestation.json", "privacy_attestation"),
        ("provider_qualification.json", "provider_qualification"),
    ):
        if (target / filename).exists() and (
            preexisting_by_kind[kind]["disposition"] != RecoveryDisposition.RECOVERED_VALID.value
        ):
            raise RecoveryError("refusing to replace a mismatched machine-local attestation record")
    writes = {
        "privacy_attestation": _write_local_record_once(
            target / "privacy_attestation.json",
            {
                "fingerprint": attestation_fingerprint,
                "approved": True,
                **required_identity,
                "approved_at_utc": approved_at,
                "evidence_ref": PUBLIC_ATTESTATION_REF,
                "evidence_fingerprint": EXPECTED_PUBLIC_ATTESTATION_SHA256,
            },
        ),
        "provider_qualification": _write_local_record_once(
            target / "provider_qualification.json",
            {
                "qualified": True,
                "fingerprint": qualification_fingerprint,
                **required_identity,
                "verified_at_utc": verified_at,
                "evidence_ref": PUBLIC_QUALIFICATION_REF,
                "evidence_fingerprint": EXPECTED_PUBLIC_QUALIFICATION_SHA256,
            },
        ),
    }
    evaluation = evaluate_attestation_recovery(
        repository_root=repository_root,
        source_attestation=repository_root / PUBLIC_ATTESTATION_REF,
        source_qualification=repository_root / PUBLIC_QUALIFICATION_REF,
        durable_attestation_path=target / "privacy_attestation.json",
        durable_qualification_path=target / "provider_qualification.json",
        verification_dir=verify,
        historical_receipt_path=repository_root / HISTORICAL_RECEIPT_REF,
        policy=policy,
    )
    if evaluation.get("accepted_for_restore") is not True:
        raise RecoveryError("machine-local attestation bootstrap did not revalidate")
    return {
        "schema_version": "1.0.0",
        "durable_dir": str(target),
        "writes": writes,
        "evaluation": evaluation,
        "cross_machine_state_imported": False,
        "secret_value_observed": False,
    }


@dataclass(frozen=True)
class CurrentAttestationPolicy:
    project_id: str = PROJECT_ID
    provider_id: str = PROVIDER_ID
    scope: str = SCOPE
    require_identity: bool = True
    require_fingerprint: bool = True
    max_age_hours: int | None = None
    requires_privacy_attestation: bool = True

    def attestation_inputs(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "provider_id": self.provider_id,
            "scope": self.scope,
            "requires_privacy_attestation": self.requires_privacy_attestation,
        }


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_current_attestation_policy(root: Path) -> CurrentAttestationPolicy:
    path = root / "config" / "cursor_takeover.json"
    if not path.is_file():
        return CurrentAttestationPolicy()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CurrentAttestationPolicy()
    if not isinstance(loaded, dict):
        return CurrentAttestationPolicy()
    max_age = loaded.get("attestation_max_age_hours")
    if not isinstance(max_age, int) or max_age <= 0:
        max_age = None
    return CurrentAttestationPolicy(
        project_id=str(loaded.get("project_id") or PROJECT_ID),
        provider_id=str(loaded.get("provider_id") or PROVIDER_ID),
        scope=str(loaded.get("attestation_scope") or SCOPE),
        require_identity=bool(loaded.get("require_attestation_identity", True)),
        require_fingerprint=bool(loaded.get("require_attestation_fingerprint", True)),
        max_age_hours=max_age,
        requires_privacy_attestation=bool(loaded.get("require_privacy_mode", True)),
    )


def load_durable_attestation(path: Path) -> DurableAttestation | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    fingerprint = payload.get("fingerprint")
    approved = payload.get("approved")
    if not isinstance(fingerprint, str) or not isinstance(approved, bool):
        return None
    return DurableAttestation(
        fingerprint=fingerprint,
        approved=approved,
        project_id=_optional_str(payload.get("project_id")),
        provider_id=_optional_str(payload.get("provider_id")),
        scope=_optional_str(payload.get("scope")),
        approved_at_utc=_optional_str(payload.get("approved_at_utc")),
        evidence_ref=_optional_str(payload.get("evidence_ref")),
        evidence_fingerprint=_optional_str(payload.get("evidence_fingerprint")),
    )


def load_durable_provider_qualification(
    path: Path,
) -> DurableProviderQualificationEvidence | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    qualified = payload.get("qualified")
    if not isinstance(qualified, bool):
        return None
    return DurableProviderQualificationEvidence(
        qualified=qualified,
        fingerprint=_optional_str(payload.get("fingerprint")),
        project_id=_optional_str(payload.get("project_id")),
        provider_id=_optional_str(payload.get("provider_id")),
        scope=_optional_str(payload.get("scope")),
        verified_at_utc=_optional_str(payload.get("verified_at_utc")),
        evidence_ref=_optional_str(payload.get("evidence_ref")),
        evidence_fingerprint=_optional_str(payload.get("evidence_fingerprint")),
    )


def copy_for_verification(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    shutil.copy2(source, destination)
    return destination


def import_exact_public_artifact(
    *,
    source: Path,
    destination: Path,
    expected_sha256: str,
    expected_byte_length: int,
) -> dict[str, Any]:
    if not source.is_file():
        raise RecoveryError(f"source artifact is missing: {source}")
    payload = source.read_bytes()
    digest = sha256_bytes(payload)
    if len(payload) != expected_byte_length or digest != expected_sha256:
        raise RecoveryError(
            "source artifact digest or length does not match the preserved expected value"
        )
    if destination.is_file():
        existing = destination.read_bytes()
        existing_digest = sha256_bytes(existing)
        if existing_digest == expected_sha256 and len(existing) == expected_byte_length:
            return {
                "applied": False,
                "idempotent": True,
                "destination": str(destination),
                "sha256": existing_digest,
                "byte_length": len(existing),
            }
        raise RecoveryError("destination already contains mismatched bytes; refusing to overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    written = destination.read_bytes()
    if sha256_bytes(written) != expected_sha256 or len(written) != expected_byte_length:
        destination.unlink(missing_ok=True)
        raise RecoveryError("post-write readback did not match the expected digest")
    return {
        "applied": True,
        "idempotent": False,
        "destination": str(destination),
        "sha256": expected_sha256,
        "byte_length": expected_byte_length,
    }


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _parse_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _classify_validation(*, valid: bool, stale: bool, present: bool) -> RecoveryDisposition:
    if not present:
        return RecoveryDisposition.MISSING
    if valid:
        return RecoveryDisposition.RECOVERED_VALID
    if stale:
        return RecoveryDisposition.RECOVERED_BUT_STALE
    return RecoveryDisposition.MISMATCHED


def evaluate_attestation_recovery(
    *,
    repository_root: Path,
    source_attestation: Path,
    source_qualification: Path,
    durable_attestation_path: Path,
    durable_qualification_path: Path,
    verification_dir: Path,
    historical_receipt_path: Path | None = None,
    policy: CurrentAttestationPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or load_current_attestation_policy(repository_root)
    verification_dir.mkdir(parents=True, exist_ok=True)
    copied_attestation = (
        copy_for_verification(source_attestation, verification_dir)
        if source_attestation.is_file()
        else None
    )
    copied_qualification = (
        copy_for_verification(source_qualification, verification_dir)
        if source_qualification.is_file()
        else None
    )

    attestation_bytes = copied_attestation.read_bytes() if copied_attestation else b""
    qualification_bytes = copied_qualification.read_bytes() if copied_qualification else b""
    attestation_digest = sha256_bytes(attestation_bytes) if attestation_bytes else None
    qualification_digest = sha256_bytes(qualification_bytes) if qualification_bytes else None
    attestation_payload = (
        _parse_json_object(copied_attestation) if copied_attestation is not None else None
    )
    qualification_payload = (
        _parse_json_object(copied_qualification) if copied_qualification is not None else None
    )
    durable_attestation = load_durable_attestation(durable_attestation_path)
    durable_qualification = load_durable_provider_qualification(durable_qualification_path)

    attestation_validation = validate_durable_attestation(
        prior=durable_attestation,
        attestation_inputs=policy.attestation_inputs(),
        require_identity=policy.require_identity,
        max_age_hours=policy.max_age_hours,
    )
    qualification_validation = validate_provider_qualification_evidence(
        evidence=durable_qualification,
        project_id=policy.project_id,
        provider_id=policy.provider_id,
        scope=policy.scope,
        require_identity=policy.require_identity,
        require_fingerprint=policy.require_fingerprint,
        max_age_hours=policy.max_age_hours,
    )

    public_attestation_ok = (
        attestation_digest == EXPECTED_PUBLIC_ATTESTATION_SHA256
        and len(attestation_bytes) == EXPECTED_PUBLIC_ATTESTATION_BYTES
        and isinstance(attestation_payload, dict)
        and attestation_payload.get("project_id") == policy.project_id
        and attestation_payload.get("provider_id") == policy.provider_id
        and attestation_payload.get("scope") == policy.scope
        and attestation_payload.get("approved") is True
    )
    public_qualification_ok = (
        qualification_digest == EXPECTED_PUBLIC_QUALIFICATION_SHA256
        and len(qualification_bytes) == EXPECTED_PUBLIC_QUALIFICATION_BYTES
        and isinstance(qualification_payload, dict)
        and qualification_payload.get("project_id") == policy.project_id
        and qualification_payload.get("provider_id") == policy.provider_id
        and qualification_payload.get("scope") == policy.scope
        and qualification_payload.get("qualified") is True
    )
    durable_attestation_match = (
        durable_attestation is not None
        and durable_attestation.evidence_fingerprint == EXPECTED_PUBLIC_ATTESTATION_SHA256
        and durable_attestation.evidence_ref == PUBLIC_ATTESTATION_REF
        and durable_attestation.fingerprint == HISTORICAL_ATTESTATION_FINGERPRINT
    )
    durable_qualification_match = (
        durable_qualification is not None
        and durable_qualification.evidence_fingerprint == EXPECTED_PUBLIC_QUALIFICATION_SHA256
        and durable_qualification.evidence_ref == PUBLIC_QUALIFICATION_REF
    )

    receipt = _historical_receipt_pairs(historical_receipt_path)
    attestation_stale = "attestation_stale" in attestation_validation.reasons
    qualification_stale = "provider_qualification_stale" in qualification_validation.reasons
    attestation_disposition = _classify_validation(
        valid=attestation_validation.valid and public_attestation_ok and durable_attestation_match,
        stale=attestation_stale and public_attestation_ok and durable_attestation_match,
        present=copied_attestation is not None or durable_attestation is not None,
    )
    qualification_disposition = _classify_validation(
        valid=(
            qualification_validation.satisfied
            and public_qualification_ok
            and durable_qualification_match
        ),
        stale=qualification_stale and public_qualification_ok and durable_qualification_match,
        present=copied_qualification is not None or durable_qualification is not None,
    )
    return {
        "schema_version": "1.0.0",
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "policy": {
            "project_id": policy.project_id,
            "provider_id": policy.provider_id,
            "scope": policy.scope,
            "require_identity": policy.require_identity,
            "require_fingerprint": policy.require_fingerprint,
            "max_age_hours": policy.max_age_hours,
        },
        "verification_dir": str(verification_dir),
        "artifacts": [
            {
                "kind": "privacy_attestation",
                "source_path": str(source_attestation),
                "verification_path": None
                if copied_attestation is None
                else str(copied_attestation),
                "preserved_sha256": attestation_digest,
                "byte_length": len(attestation_bytes) if attestation_bytes else 0,
                "expected_sha256": EXPECTED_PUBLIC_ATTESTATION_SHA256,
                "expected_byte_length": EXPECTED_PUBLIC_ATTESTATION_BYTES,
                "public_schema_valid": public_attestation_ok,
                "durable_record_path": str(durable_attestation_path),
                "durable_record_match": durable_attestation_match,
                "historical_receipt_match": receipt["attestation_match"],
                "validator_valid": attestation_validation.valid,
                "validator_state": attestation_validation.state.value,
                "validator_reasons": list(attestation_validation.reasons),
                "current_policy_state": (
                    "VALID"
                    if attestation_disposition is RecoveryDisposition.RECOVERED_VALID
                    else attestation_disposition.value
                ),
                "disposition": attestation_disposition.value,
            },
            {
                "kind": "provider_qualification",
                "source_path": str(source_qualification),
                "verification_path": None
                if copied_qualification is None
                else str(copied_qualification),
                "preserved_sha256": qualification_digest,
                "byte_length": len(qualification_bytes) if qualification_bytes else 0,
                "expected_sha256": EXPECTED_PUBLIC_QUALIFICATION_SHA256,
                "expected_byte_length": EXPECTED_PUBLIC_QUALIFICATION_BYTES,
                "public_schema_valid": public_qualification_ok,
                "durable_record_path": str(durable_qualification_path),
                "durable_record_match": durable_qualification_match,
                "historical_receipt_match": receipt["qualification_match"],
                "validator_valid": qualification_validation.satisfied,
                "validator_state": qualification_validation.state.value,
                "validator_reasons": list(qualification_validation.reasons),
                "current_policy_state": (
                    "VALID"
                    if qualification_disposition is RecoveryDisposition.RECOVERED_VALID
                    else qualification_disposition.value
                ),
                "disposition": qualification_disposition.value,
            },
        ],
        "accepted_for_restore": (
            attestation_disposition is RecoveryDisposition.RECOVERED_VALID
            and qualification_disposition is RecoveryDisposition.RECOVERED_VALID
        ),
    }


def restore_accepted_public_artifacts(
    *,
    evaluation: dict[str, Any],
    repository_root: Path,
    source_attestation: Path,
    source_qualification: Path,
) -> dict[str, Any]:
    if not evaluation.get("accepted_for_restore"):
        raise RecoveryError("refusing to restore artifacts that are not RECOVERED_VALID")
    attestation_result = import_exact_public_artifact(
        source=source_attestation,
        destination=repository_root / PUBLIC_ATTESTATION_REF,
        expected_sha256=EXPECTED_PUBLIC_ATTESTATION_SHA256,
        expected_byte_length=EXPECTED_PUBLIC_ATTESTATION_BYTES,
    )
    qualification_result = import_exact_public_artifact(
        source=source_qualification,
        destination=repository_root / PUBLIC_QUALIFICATION_REF,
        expected_sha256=EXPECTED_PUBLIC_QUALIFICATION_SHA256,
        expected_byte_length=EXPECTED_PUBLIC_QUALIFICATION_BYTES,
    )
    provenance = {
        "schema_version": "1.0.0",
        "recovered_at_utc": datetime.now(UTC).isoformat(),
        "source_attestation": str(source_attestation),
        "source_qualification": str(source_qualification),
        "attestation_sha256": EXPECTED_PUBLIC_ATTESTATION_SHA256,
        "qualification_sha256": EXPECTED_PUBLIC_QUALIFICATION_SHA256,
        "method": "exact_byte_import",
        "hand_edited": False,
        "evaluation_dispositions": [
            item["disposition"] for item in evaluation.get("artifacts", [])
        ],
        "attestation_import": attestation_result,
        "qualification_import": qualification_result,
    }
    provenance_path = repository_root / PROVENANCE_REF
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return provenance


def recover_and_restore(
    *,
    repository_root: Path,
    source_root: Path | None = None,
    durable_dir: Path | None = None,
    verification_dir: Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    source_root = source_root or DEFAULT_PRESERVATION_ROOT
    durable_dir = resolve_durable_dir(repository_root, durable_dir)
    verification_dir = verification_dir or (
        repository_root / ".local" / "attestation_recovery_verify"
    )
    evaluation = evaluate_attestation_recovery(
        repository_root=repository_root,
        source_attestation=source_root / PUBLIC_ATTESTATION_REF,
        source_qualification=source_root / PUBLIC_QUALIFICATION_REF,
        durable_attestation_path=durable_dir / "privacy_attestation.json",
        durable_qualification_path=durable_dir / "provider_qualification.json",
        verification_dir=verification_dir,
        historical_receipt_path=repository_root / HISTORICAL_RECEIPT_REF,
    )
    result = {"evaluation": evaluation, "restore": None, "applied": False}
    if apply:
        result["restore"] = restore_accepted_public_artifacts(
            evaluation=evaluation,
            repository_root=repository_root,
            source_attestation=source_root / PUBLIC_ATTESTATION_REF,
            source_qualification=source_root / PUBLIC_QUALIFICATION_REF,
        )
        result["applied"] = True
    return result


def _historical_receipt_pairs(path: Path | None) -> dict[str, bool]:
    empty = {"attestation_match": False, "qualification_match": False}
    if path is None or not path.is_file():
        return empty
    payload = _parse_json_object(path)
    if payload is None:
        return empty
    attestation = (
        payload.get("takeover_governor", {}).get("attestation", {}).get("evidence_reference", {})
    )
    qualification = (
        payload.get("takeover_governor", {})
        .get("provider_dispatch", {})
        .get("qualification_evidence", {})
        .get("reference_validation", {})
    )
    return {
        "attestation_match": (
            attestation.get("fingerprint_expected") == EXPECTED_PUBLIC_ATTESTATION_SHA256
            and attestation.get("fingerprint_actual") == EXPECTED_PUBLIC_ATTESTATION_SHA256
            and attestation.get("fingerprint_matches") is True
        ),
        "qualification_match": (
            qualification.get("fingerprint_expected") == EXPECTED_PUBLIC_QUALIFICATION_SHA256
            and qualification.get("fingerprint_actual") == EXPECTED_PUBLIC_QUALIFICATION_SHA256
            and qualification.get("fingerprint_matches") is True
        ),
    }
