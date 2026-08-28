"""Coverage for candidate-bound release evidence at the pre-admission gate.

Scan evidence, provenance, and artifact integrity records exist only once the
release artifacts are built. These tests prove the gate genuinely verifies
them against real artifact bytes: absent evidence fails closed, complete
evidence passes, and evidence not bound to this exact source, SBOM, or
artifacts is rejected.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_pipeline.domain.security import (
    ArtifactIntegrityRecord,
    ProvenanceEvidenceBinding,
    ProvenanceEvidenceKind,
    ReleaseProvenance,
    ScannerEvidence,
    SupplyChainFindingKind,
)
from project_pipeline.release_hardening.pre_admission import (
    CandidateReleaseEvidence,
    PreAdmissionState,
    evaluate_pre_admission_release_gate,
)
from project_pipeline.security.supply_chain import (
    _manifest_aggregate,
    _sbom_sha256,
    build_repository_sbom,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_KINDS = (
    SupplyChainFindingKind.VULNERABILITY,
    SupplyChainFindingKind.MISCONFIGURATION,
)


def _identifier(prefix: str, seed: str) -> str:
    return f"{prefix}-{hashlib.sha256(seed.encode()).hexdigest()[:20].upper()}"


@pytest.fixture
def artifacts() -> Iterator[tuple[Path, ...]]:
    """Write real candidate artifact bytes; the gate hashes them from disk.

    The gate rejects artifact paths outside the repository root, so these are
    built inside it and removed afterwards.
    """

    directory = REPO_ROOT / ".pytest-candidate-artifacts"
    directory.mkdir(exist_ok=True)
    built = []
    for name, payload in (
        ("project_pipeline-0.0.0-py3-none-any.whl", b"wheel-bytes"),
        ("project_pipeline-0.0.0.tar.gz", b"sdist-bytes"),
    ):
        path = directory / name
        path.write_bytes(payload)
        built.append(path)
    try:
        yield tuple(built)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _integrity_records(
    artifacts: tuple[Path, ...], provenance_id: str | None
) -> tuple[ArtifactIntegrityRecord, ...]:
    return tuple(
        ArtifactIntegrityRecord(
            integrity_id=_identifier("INTEGRITY", path.name),
            artifact_path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            size_bytes=path.stat().st_size,
            signature_state="NOT_REQUIRED",
            provenance_id=provenance_id,
        )
        for path in artifacts
    )


def _candidate_evidence(
    artifacts: tuple[Path, ...],
    *,
    aggregate: str | None = None,
    sbom_sha256: str | None = None,
    verification_state: str = "VERIFIED",
    scan_state: str = "SUCCEEDED",
    bind_provenance: bool = True,
    declared: tuple[str, ...] | None = None,
) -> CandidateReleaseEvidence:
    real_aggregate = _manifest_aggregate(REPO_ROOT)
    real_sbom_sha = _sbom_sha256(build_repository_sbom(REPO_ROOT))
    provenance_id = _identifier("PROV", "candidate-evidence-test")
    records = _integrity_records(artifacts, provenance_id if bind_provenance else None)
    paths = declared if declared is not None else tuple(str(path) for path in artifacts)
    observed = datetime.now(UTC)
    result_sha256 = hashlib.sha256(b"scan-result").hexdigest()
    scan = ScannerEvidence(
        scanner_evidence_id=_identifier("SCANEVID", "candidate-scan-test"),
        tool="test-scanner",
        execution_state=scan_state,
        source_manifest_sha256=aggregate or real_aggregate,
        result_sha256=result_sha256,
        observed_at_utc=observed,
        scanned_kinds=REQUIRED_KINDS,
        findings=(),
        evidence_path="evidence/candidate_scan.json",
    )
    bindings = (
        ProvenanceEvidenceBinding(
            evidence_id=scan.scanner_evidence_id,
            evidence_kind=ProvenanceEvidenceKind.SCANNER,
            source_manifest_sha256=aggregate or real_aggregate,
            result_sha256=result_sha256,
            tool=scan.tool,
            observed_at_utc=observed,
        ),
        *(
            ProvenanceEvidenceBinding(
                evidence_id=record.integrity_id,
                evidence_kind=ProvenanceEvidenceKind.INTEGRITY,
                source_manifest_sha256=aggregate or real_aggregate,
                result_sha256=record.sha256,
                tool="integrity",
                observed_at_utc=observed,
            )
            for record in records
        ),
    )
    provenance = ReleaseProvenance(
        provenance_id=provenance_id,
        project_id="project-pipeline",
        source_aggregate_sha256=aggregate or real_aggregate,
        builder_identity_id="BUILDER-TEST",
        sbom_sha256=sbom_sha256 or real_sbom_sha,
        verification_state=verification_state,
        evidence_ids=tuple(binding.evidence_id for binding in bindings),
        declared_artifact_paths=paths,
        artifact_integrity_ids=tuple(sorted(record.integrity_id for record in records)),
        evidence_bindings=bindings,
        required_signature_state="NOT_REQUIRED",
    )
    return CandidateReleaseEvidence(
        scanner_evidence=(scan,),
        integrity_records=records,
        provenance=provenance,
        release_artifact_paths=paths,
        signing_profile_enabled=False,
        scanner_target_coverage={
            scan.scanner_evidence_id: ("source", "dependency", "container", "infrastructure")
        },
    )


def test_absent_candidate_evidence_fails_closed() -> None:
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT)
    assert verdict.state is PreAdmissionState.FAIL
    joined = " ".join(verdict.blockers)
    assert "scan evidence" in joined
    assert "provenance" in joined
    assert "integrity" in joined


def test_blockers_name_the_specific_missing_evidence() -> None:
    """A generic 'evidence is incomplete' string hides which record is missing."""

    verdict = evaluate_pre_admission_release_gate(REPO_ROOT)
    assert verdict.blockers
    assert all(blocker.startswith("release supply-chain: ") for blocker in verdict.blockers)


def test_complete_candidate_evidence_passes_pre_admission(artifacts: tuple[Path, ...]) -> None:
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, _candidate_evidence(artifacts))
    assert verdict.state is PreAdmissionState.PASS, verdict.blockers
    assert verdict.supply_chain_state == "PASS"
    assert verdict.blockers == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"aggregate": "0" * 64}, id="not-bound-to-this-source"),
        pytest.param({"sbom_sha256": "1" * 64}, id="not-bound-to-this-sbom"),
        pytest.param({"verification_state": "UNVERIFIED"}, id="provenance-unverified"),
        pytest.param({"scan_state": "FAILED"}, id="scan-did-not-succeed"),
        pytest.param({"bind_provenance": False}, id="integrity-not-bound-to-provenance"),
    ],
)
def test_unbound_or_unverified_evidence_is_rejected(
    artifacts: tuple[Path, ...], kwargs: dict[str, object]
) -> None:
    verdict = evaluate_pre_admission_release_gate(
        REPO_ROOT, _candidate_evidence(artifacts, **kwargs)
    )
    assert verdict.state is not PreAdmissionState.PASS
    assert verdict.blockers


def test_artifact_bytes_must_match_the_integrity_record(artifacts: tuple[Path, ...]) -> None:
    evidence = _candidate_evidence(artifacts)
    # Rewrite one artifact after the record was produced.
    artifacts[0].write_bytes(b"tampered-bytes")
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, evidence)
    assert verdict.state is not PreAdmissionState.PASS
    assert verdict.blockers


def test_missing_artifact_file_is_surfaced(artifacts: tuple[Path, ...]) -> None:
    evidence = _candidate_evidence(artifacts)
    artifacts[0].unlink()
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, evidence)
    assert verdict.state is not PreAdmissionState.PASS
    assert verdict.blockers
