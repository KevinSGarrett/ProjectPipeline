"""Coverage for the production candidate-release-evidence producer.

The pre-admission gate verifies scanner, provenance, and integrity records
against real artifact bytes. These tests prove the producer binds them to this
checkout and these bytes, and that tampering is still rejected.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.domain.security import SupplyChainFindingKind
from project_pipeline.release_hardening.candidate_evidence import (
    CandidateEvidenceError,
    ScannerRun,
    build_candidate_release_evidence,
)
from project_pipeline.release_hardening.pre_admission import (
    PreAdmissionState,
    evaluate_pre_admission_release_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TARGETS = ("source", "dependency", "container", "infrastructure")


@pytest.fixture
def artifacts() -> Iterator[tuple[Path, ...]]:
    directory = REPO_ROOT / ".pytest-producer-artifacts"
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


def _trivy_payload() -> dict[str, object]:
    """A minimal, well-formed Trivy report with no findings."""

    return {"SchemaVersion": 2, "ArtifactName": ".", "ArtifactType": "filesystem", "Results": []}


def _scanner_run(**overrides: object) -> ScannerRun:
    defaults: dict[str, object] = {
        "tool": "trivy",
        "payload": _trivy_payload(),
        "target_classes": REQUIRED_TARGETS,
        "evidence_path": "evidence/release_scan.json",
        "scanned_kinds": (
            SupplyChainFindingKind.VULNERABILITY,
            SupplyChainFindingKind.MISCONFIGURATION,
        ),
        "execution_state": "SUCCEEDED",
    }
    defaults.update(overrides)
    return ScannerRun(**defaults)  # type: ignore[arg-type]


def test_producer_binds_provenance_and_integrity_to_real_bytes(
    artifacts: tuple[Path, ...],
) -> None:
    bundle = build_candidate_release_evidence(
        REPO_ROOT,
        artifact_paths=artifacts,
        builder_identity_id="actor:test",
    )
    assert bundle.provenance.verification_state == "VERIFIED"
    assert len(bundle.integrity_records) == len(artifacts)
    assert all(
        record.provenance_id == bundle.provenance.provenance_id
        for record in bundle.integrity_records
    )
    assert tuple(sorted(bundle.provenance.artifact_integrity_ids)) == tuple(
        sorted(record.integrity_id for record in bundle.integrity_records)
    )
    # Every declared artifact is bound by a typed integrity evidence binding.
    bound = {binding.evidence_id for binding in bundle.provenance.evidence_bindings}
    assert {record.integrity_id for record in bundle.integrity_records} <= bound


def test_provenance_and_integrity_findings_are_cleared(artifacts: tuple[Path, ...]) -> None:
    """Without a scanner the gate must fail on scan evidence only."""

    bundle = build_candidate_release_evidence(
        REPO_ROOT,
        artifact_paths=artifacts,
        builder_identity_id="actor:test",
    )
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    joined = " ".join(verdict.blockers)
    assert "integrity" not in joined
    assert "provenance" not in joined
    assert "scan evidence" in joined


def test_complete_evidence_with_real_scanner_run_passes(artifacts: tuple[Path, ...]) -> None:
    bundle = build_candidate_release_evidence(
        REPO_ROOT,
        artifact_paths=artifacts,
        scanner_runs=(_scanner_run(),),
        builder_identity_id="actor:test",
    )
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is PreAdmissionState.PASS, verdict.blockers
    assert verdict.supply_chain_state == "PASS"


def test_partial_target_coverage_is_rejected(artifacts: tuple[Path, ...]) -> None:
    """Declaring fewer classes than required must not pass."""

    bundle = build_candidate_release_evidence(
        REPO_ROOT,
        artifact_paths=artifacts,
        scanner_runs=(_scanner_run(target_classes=("source",)),),
        builder_identity_id="actor:test",
    )
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is not PreAdmissionState.PASS


def test_failed_scan_is_rejected(artifacts: tuple[Path, ...]) -> None:
    bundle = build_candidate_release_evidence(
        REPO_ROOT,
        artifact_paths=artifacts,
        scanner_runs=(_scanner_run(execution_state="FAILED"),),
        builder_identity_id="actor:test",
    )
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is not PreAdmissionState.PASS


def test_stale_scan_is_rejected(artifacts: tuple[Path, ...]) -> None:
    stale = datetime.now(UTC) - timedelta(days=3)
    bundle = build_candidate_release_evidence(
        REPO_ROOT,
        artifact_paths=artifacts,
        scanner_runs=(_scanner_run(observed_at_utc=stale),),
        builder_identity_id="actor:test",
    )
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is not PreAdmissionState.PASS


def test_tampered_artifact_bytes_are_rejected(artifacts: tuple[Path, ...]) -> None:
    bundle = build_candidate_release_evidence(
        REPO_ROOT,
        artifact_paths=artifacts,
        scanner_runs=(_scanner_run(),),
        builder_identity_id="actor:test",
    )
    artifacts[0].write_bytes(b"tampered-bytes")
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is not PreAdmissionState.PASS


def test_artifact_outside_repository_root_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "project_pipeline-0.0.0-py3-none-any.whl"
    outside.write_bytes(b"wheel-bytes")
    with pytest.raises(CandidateEvidenceError):
        build_candidate_release_evidence(
            REPO_ROOT,
            artifact_paths=(outside,),
            builder_identity_id="actor:test",
        )


def test_no_artifacts_fails_closed() -> None:
    with pytest.raises(CandidateEvidenceError):
        build_candidate_release_evidence(
            REPO_ROOT,
            artifact_paths=(),
            builder_identity_id="actor:test",
        )


def test_unsupported_scanner_is_rejected(artifacts: tuple[Path, ...]) -> None:
    with pytest.raises(CandidateEvidenceError):
        build_candidate_release_evidence(
            REPO_ROOT,
            artifact_paths=artifacts,
            scanner_runs=(_scanner_run(tool="not-a-governed-scanner"),),
            builder_identity_id="actor:test",
        )


def test_evidence_is_json_serializable(artifacts: tuple[Path, ...]) -> None:
    bundle = build_candidate_release_evidence(
        REPO_ROOT,
        artifact_paths=artifacts,
        scanner_runs=(_scanner_run(),),
        builder_identity_id="actor:test",
    )
    json.dumps(bundle.provenance.model_dump(mode="json"))
