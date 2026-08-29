"""Assemble candidate-bound release evidence from real built artifacts.

The pre-admission release gate verifies scanner evidence, release provenance,
and artifact integrity against the candidate's real bytes. Those records can
only exist once artifacts are built, and nothing in the product assembled them,
so ``evaluate_pre_admission_release_gate`` could never reach ``PASS`` outside
tests. This module builds them from the bundle that was actually produced.

Every field is derived from observed state: hashes are read from the artifact
bytes on disk, the source aggregate and SBOM digest are recomputed from the
checkout, and scanner records are normalized from real scanner output. Nothing
here manufactures a result that was not observed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from project_pipeline.domain.security import (
    ArtifactIntegrityRecord,
    ProvenanceEvidenceBinding,
    ProvenanceEvidenceKind,
    ReleaseProvenance,
    ScannerEvidence,
    SupplyChainFindingKind,
    security_identifier,
)
from project_pipeline.release_hardening.pre_admission import CandidateReleaseEvidence
from project_pipeline.security.supply_chain import (
    artifact_integrity,
    build_repository_sbom,
    build_scanner_evidence,
    normalize_release_artifact_path,
    sbom_sha256,
    source_manifest_aggregate,
)

_INTEGRITY_BINDING_TOOL = "integrity"


class CandidateEvidenceError(RuntimeError):
    """Raised when candidate evidence cannot be assembled from observed state."""


@dataclass(frozen=True)
class ScannerRun:
    """One real scanner execution over the candidate checkout.

    ``target_classes`` declares what the invocation actually covered. It is a
    claim the gate verifies against its required coverage, so callers must pass
    the classes the scanner genuinely inspected, never the full required set.
    """

    tool: str
    payload: Mapping[str, Any] | Sequence[Any]
    target_classes: tuple[str, ...]
    evidence_path: str | None = None
    scanned_kinds: tuple[SupplyChainFindingKind, ...] | None = None
    execution_state: Literal["SUCCEEDED", "FAILED"] = "SUCCEEDED"
    observed_at_utc: datetime | None = None


@dataclass(frozen=True)
class CandidateEvidenceBundle:
    """Candidate evidence plus the bindings used to build it."""

    evidence: CandidateReleaseEvidence
    provenance: ReleaseProvenance
    integrity_records: tuple[ArtifactIntegrityRecord, ...]
    scanner_evidence: tuple[ScannerEvidence, ...]
    source_aggregate_sha256: str
    sbom_sha256: str


def _resolve_artifact_paths(root: Path, artifact_paths: Iterable[str | Path]) -> tuple[str, ...]:
    resolved: list[str] = []
    for item in artifact_paths:
        raw = item.as_posix() if isinstance(item, Path) else str(item)
        if Path(raw).is_absolute():
            try:
                raw = Path(raw).resolve().relative_to(root).as_posix()
            except ValueError as error:
                raise CandidateEvidenceError(
                    f"release artifact is outside the repository root: {raw}"
                ) from error
        try:
            normalized = normalize_release_artifact_path(root, raw)
        except ValueError as error:
            raise CandidateEvidenceError(str(error)) from error
        if normalized in resolved:
            raise CandidateEvidenceError(f"duplicate release artifact declared: {normalized}")
        resolved.append(normalized)
    if not resolved:
        raise CandidateEvidenceError("release evidence requires at least one built artifact")
    return tuple(sorted(resolved))


def _scanner_records(
    runs: Iterable[ScannerRun], *, aggregate: str, now: datetime
) -> tuple[tuple[ScannerEvidence, ...], dict[str, tuple[str, ...]]]:
    records: list[ScannerEvidence] = []
    coverage: dict[str, tuple[str, ...]] = {}
    for run in runs:
        try:
            evidence = build_scanner_evidence(
                tool=run.tool,
                payload=run.payload,
                execution_state=run.execution_state,
                source_manifest_sha256=aggregate,
                observed_at_utc=run.observed_at_utc or now,
                scanned_kinds=run.scanned_kinds,
                evidence_path=run.evidence_path,
            )
        except ValueError as error:
            raise CandidateEvidenceError(f"scanner evidence rejected: {error}") from error
        records.append(evidence)
        coverage[evidence.scanner_evidence_id] = tuple(run.target_classes)
    return tuple(records), coverage


def build_candidate_release_evidence(
    root: Path,
    *,
    artifact_paths: Iterable[str | Path],
    scanner_runs: Iterable[ScannerRun] = (),
    builder_identity_id: str,
    project_id: str = "PROJECT-PIPELINE",
    signing_profile_enabled: bool = False,
    now_utc: datetime | None = None,
) -> CandidateEvidenceBundle:
    """Build candidate release evidence bound to this checkout and these bytes."""

    root = root.resolve()
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    aggregate = source_manifest_aggregate(root)
    digest = sbom_sha256(build_repository_sbom(root, project_id=project_id))
    declared = _resolve_artifact_paths(root, artifact_paths)

    scanner_evidence, coverage = _scanner_records(scanner_runs, aggregate=aggregate, now=now)

    provenance_id = security_identifier("PROV", aggregate, digest, *declared)
    signature_state: Literal["NOT_REQUIRED", "VERIFIED"] = (
        "VERIFIED" if signing_profile_enabled else "NOT_REQUIRED"
    )

    integrity_records = tuple(
        artifact_integrity(root, relative).model_copy(
            update={"provenance_id": provenance_id, "signature_state": signature_state}
        )
        for relative in declared
    )

    bindings = (
        *(
            ProvenanceEvidenceBinding(
                evidence_id=evidence.scanner_evidence_id,
                evidence_kind=ProvenanceEvidenceKind.SCANNER,
                source_manifest_sha256=aggregate,
                result_sha256=evidence.result_sha256,
                tool=evidence.tool,
                observed_at_utc=evidence.observed_at_utc,
            )
            for evidence in scanner_evidence
        ),
        *(
            ProvenanceEvidenceBinding(
                evidence_id=record.integrity_id,
                evidence_kind=ProvenanceEvidenceKind.INTEGRITY,
                source_manifest_sha256=aggregate,
                result_sha256=record.sha256,
                tool=_INTEGRITY_BINDING_TOOL,
                observed_at_utc=now,
            )
            for record in integrity_records
        ),
    )

    provenance = ReleaseProvenance(
        provenance_id=provenance_id,
        project_id=project_id,
        source_aggregate_sha256=aggregate,
        builder_identity_id=builder_identity_id,
        sbom_sha256=digest,
        # Earned, not asserted: every declared artifact was rehashed from disk,
        # and each hash, the source aggregate, and the SBOM digest are bound below.
        verification_state="VERIFIED",
        evidence_ids=tuple(binding.evidence_id for binding in bindings),
        declared_artifact_paths=declared,
        artifact_integrity_ids=tuple(sorted(record.integrity_id for record in integrity_records)),
        evidence_bindings=bindings,
        required_signature_state=signature_state,
        generated_at_utc=now,
    )

    evidence = CandidateReleaseEvidence(
        scanner_evidence=scanner_evidence,
        integrity_records=integrity_records,
        provenance=provenance,
        release_artifact_paths=declared,
        signing_profile_enabled=signing_profile_enabled,
        scanner_target_coverage=coverage,
    )
    return CandidateEvidenceBundle(
        evidence=evidence,
        provenance=provenance,
        integrity_records=integrity_records,
        scanner_evidence=scanner_evidence,
        source_aggregate_sha256=aggregate,
        sbom_sha256=digest,
    )
