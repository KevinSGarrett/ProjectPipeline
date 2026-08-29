"""Assemble candidate-bound release evidence from real built artifacts.

The pre-admission release gate verifies scanner evidence, release provenance,
and artifact integrity against the candidate's real bytes. Those records can
only exist once artifacts are built, and nothing in the product assembled them,
so ``evaluate_pre_admission_release_gate`` could never reach ``PASS`` outside
tests. This module builds them from the bundle that was actually produced.

Every field is derived from observed state: hashes are read from the artifact
bytes on disk, the source aggregate and SBOM digest are recomputed from the
checkout, target-class coverage is inferred from the scanner's own report, and
signature state is only ever reported as verified when a verifier says so.
Nothing here manufactures a result that was not observed.
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

SignatureState = Literal["NOT_REQUIRED", "UNVERIFIED", "VERIFIED", "FAILED"]

# Trivy reports the configuration language it parsed. Map that to the release
# target class the finding actually proves coverage of.
_TRIVY_CONFIG_TARGETS: Mapping[str, str] = {
    "dockerfile": "container",
    "docker": "container",
    "terraform": "infrastructure",
    "terraformplan": "infrastructure",
    "cloudformation": "infrastructure",
    "kubernetes": "infrastructure",
    "helm": "infrastructure",
    "azure-arm": "infrastructure",
}


class CandidateEvidenceError(RuntimeError):
    """Raised when candidate evidence cannot be assembled from observed state."""


@dataclass(frozen=True)
class ScannerRun:
    """One real scanner execution over the candidate checkout.

    ``target_classes`` declares what the invocation covered. It is not taken on
    trust: the declared classes are checked against the classes the scanner's
    own report proves it inspected, so a run cannot overclaim coverage.
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


def _require_aware(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CandidateEvidenceError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _trivy_covered_targets(payload: Mapping[str, Any] | Sequence[Any]) -> frozenset[str]:
    """Infer the target classes a Trivy report proves were inspected."""

    if not isinstance(payload, Mapping):
        return frozenset()
    results = payload.get("Results")
    if not isinstance(results, list):
        return frozenset()
    covered: set[str] = set()
    for entry in results:
        if not isinstance(entry, Mapping):
            continue
        result_class = str(entry.get("Class") or "").strip().casefold()
        result_type = str(entry.get("Type") or "").strip().casefold()
        if result_class == "lang-pkgs":
            covered.add("dependency")
        elif result_class == "os-pkgs":
            covered.add("container")
        elif result_class in {"config", "secret", "license"}:
            mapped = _TRIVY_CONFIG_TARGETS.get(result_type)
            if mapped:
                covered.add(mapped)
    # A filesystem or repository scan walks the source tree itself.
    artifact_type = str(payload.get("ArtifactType") or "").strip().casefold()
    if artifact_type in {"filesystem", "repository"}:
        covered.add("source")
    if artifact_type in {"container_image", "image"}:
        covered.add("container")
    return frozenset(covered)


def _covered_targets(tool: str, payload: Mapping[str, Any] | Sequence[Any]) -> frozenset[str]:
    if tool.strip().casefold() == "trivy":
        return _trivy_covered_targets(payload)
    # Other governed scanners do not describe target classes in their reports,
    # so their declared coverage cannot be corroborated here.
    return frozenset()


def _resolve_artifact_paths(root: Path, artifact_paths: Iterable[str | Path]) -> tuple[str, ...]:
    resolved: list[str] = []
    seen: set[str] = set()
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
        # Windows paths differ only by case for the same file on disk.
        key = normalized.casefold()
        if key in seen:
            raise CandidateEvidenceError(f"duplicate release artifact declared: {normalized}")
        seen.add(key)
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
        declared = tuple(dict.fromkeys(item.strip().casefold() for item in run.target_classes))
        corroborated = _covered_targets(run.tool, run.payload)
        if corroborated:
            overclaimed = sorted(set(declared) - corroborated)
            if overclaimed:
                raise CandidateEvidenceError(
                    f"{run.tool} report does not prove coverage for declared target classes: "
                    + ", ".join(overclaimed)
                )
        observed = (
            _require_aware(run.observed_at_utc, field="scanner observation time")
            if run.observed_at_utc is not None
            else now
        )
        try:
            evidence = build_scanner_evidence(
                tool=run.tool,
                payload=run.payload,
                execution_state=run.execution_state,
                source_manifest_sha256=aggregate,
                observed_at_utc=observed,
                scanned_kinds=run.scanned_kinds,
                evidence_path=run.evidence_path,
            )
        except ValueError as error:
            raise CandidateEvidenceError(f"scanner evidence rejected: {error}") from error
        records.append(evidence)
        coverage[evidence.scanner_evidence_id] = declared
    return tuple(records), coverage


def build_candidate_release_evidence(
    root: Path,
    *,
    artifact_paths: Iterable[str | Path],
    scanner_runs: Iterable[ScannerRun] = (),
    builder_identity_id: str,
    project_id: str = "PROJECT-PIPELINE",
    signing_profile_enabled: bool = False,
    verified_signature_paths: Iterable[str] = (),
    now_utc: datetime | None = None,
) -> CandidateEvidenceBundle:
    """Build candidate release evidence bound to this checkout and these bytes.

    ``verified_signature_paths`` must come from a real signature verification.
    Artifacts absent from it are reported ``UNVERIFIED`` when a signing profile
    is enabled, so the gate — not this producer — decides whether that is
    acceptable.
    """

    root = root.resolve()
    now = (
        _require_aware(now_utc, field="evidence generation time")
        if now_utc is not None
        else datetime.now(UTC)
    )
    aggregate = source_manifest_aggregate(root)
    digest = sbom_sha256(build_repository_sbom(root, project_id=project_id))
    declared = _resolve_artifact_paths(root, artifact_paths)

    scanner_evidence, coverage = _scanner_records(scanner_runs, aggregate=aggregate, now=now)

    verified_signatures = {
        normalize_release_artifact_path(root, item).casefold() for item in verified_signature_paths
    }

    base_records = tuple(artifact_integrity(root, relative) for relative in declared)

    provenance_id = security_identifier(
        "PROV",
        project_id,
        aggregate,
        builder_identity_id,
        digest,
        now.isoformat(),
        *(f"{record.artifact_path}:{record.sha256}" for record in base_records),
    )

    def _signature_state(relative: str) -> SignatureState:
        if not signing_profile_enabled:
            return "NOT_REQUIRED"
        return "VERIFIED" if relative.casefold() in verified_signatures else "UNVERIFIED"

    integrity_records = tuple(
        record.model_copy(
            update={
                "provenance_id": provenance_id,
                "signature_state": _signature_state(record.artifact_path),
            }
        )
        for record in base_records
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
        # Locally derived: this process rehashed the artifacts and recomputed
        # the source and SBOM digests. No independent attestation is claimed.
        verification_state="VERIFIED_LOCAL",
        evidence_ids=tuple(binding.evidence_id for binding in bindings),
        declared_artifact_paths=declared,
        artifact_integrity_ids=tuple(sorted(record.integrity_id for record in integrity_records)),
        evidence_bindings=bindings,
        required_signature_state="VERIFIED" if signing_profile_enabled else "NOT_REQUIRED",
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
