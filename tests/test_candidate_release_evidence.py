"""Coverage for the production candidate-release-evidence producer.

The pre-admission gate verifies scanner, provenance, and integrity records
against real artifact bytes. These tests prove the producer binds them to this
checkout and these bytes, that it never claims verification it did not perform,
and that tampering and overclaimed coverage are rejected.
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
    # dist/ is git-ignored, so fixture bytes cannot perturb the source manifest.
    directory = REPO_ROOT / "dist" / "pytest-producer-artifacts"
    directory.mkdir(parents=True, exist_ok=True)
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
    """A well-formed Trivy report proving all four required target classes."""

    return {
        "SchemaVersion": 2,
        "ArtifactName": ".",
        "ArtifactType": "filesystem",
        "Results": [
            {"Target": "uv.lock", "Class": "lang-pkgs", "Type": "uv", "Vulnerabilities": []},
            {
                "Target": "infrastructure/docker/Dockerfile",
                "Class": "config",
                "Type": "dockerfile",
                "Misconfigurations": [],
            },
            {
                "Target": "infrastructure/aws/terraform",
                "Class": "config",
                "Type": "terraform",
                "Misconfigurations": [],
            },
        ],
    }


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


def _build(artifacts: tuple[Path, ...], **overrides: object):
    kwargs: dict[str, object] = {
        "artifact_paths": artifacts,
        "builder_identity_id": "actor:test",
    }
    kwargs.update(overrides)
    return build_candidate_release_evidence(REPO_ROOT, **kwargs)  # type: ignore[arg-type]


def test_producer_binds_provenance_and_integrity_to_real_bytes(
    artifacts: tuple[Path, ...],
) -> None:
    bundle = _build(artifacts)
    assert len(bundle.integrity_records) == len(artifacts)
    assert all(
        record.provenance_id == bundle.provenance.provenance_id
        for record in bundle.integrity_records
    )
    assert tuple(sorted(bundle.provenance.artifact_integrity_ids)) == tuple(
        sorted(record.integrity_id for record in bundle.integrity_records)
    )
    bound = {binding.evidence_id for binding in bundle.provenance.evidence_bindings}
    assert {record.integrity_id for record in bundle.integrity_records} <= bound


def test_verification_state_claims_only_local_derivation(artifacts: tuple[Path, ...]) -> None:
    """The producer rehashes locally; it must not claim independent attestation."""

    bundle = _build(artifacts)
    assert bundle.provenance.verification_state == "VERIFIED_LOCAL"


def test_provenance_id_distinguishes_builder_identity(artifacts: tuple[Path, ...]) -> None:
    fixed = datetime.now(UTC)
    first = _build(artifacts, builder_identity_id="actor:one", now_utc=fixed)
    second = _build(artifacts, builder_identity_id="actor:two", now_utc=fixed)
    assert first.provenance.provenance_id != second.provenance.provenance_id


def test_provenance_and_integrity_findings_are_cleared(artifacts: tuple[Path, ...]) -> None:
    """Without a scanner the gate must fail on scan evidence only."""

    bundle = _build(artifacts)
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    joined = " ".join(verdict.blockers)
    assert "integrity" not in joined
    assert "provenance" not in joined
    assert "scan evidence" in joined


def test_complete_evidence_with_real_scanner_run_passes(artifacts: tuple[Path, ...]) -> None:
    bundle = _build(artifacts, scanner_runs=(_scanner_run(),))
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is PreAdmissionState.PASS, verdict.blockers
    assert verdict.supply_chain_state == "PASS"


def test_unsigned_artifacts_do_not_satisfy_an_enabled_signing_profile(
    artifacts: tuple[Path, ...],
) -> None:
    """Enabling signing must not auto-satisfy the signature requirement."""

    bundle = _build(
        artifacts,
        scanner_runs=(_scanner_run(),),
        signing_profile_enabled=True,
    )
    assert all(record.signature_state == "UNVERIFIED" for record in bundle.integrity_records)
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is not PreAdmissionState.PASS


def test_signature_state_verified_only_from_a_real_verification(
    artifacts: tuple[Path, ...],
) -> None:
    bundle = _build(
        artifacts,
        scanner_runs=(_scanner_run(),),
        signing_profile_enabled=True,
        verified_signature_paths=[
            path.resolve().relative_to(REPO_ROOT).as_posix() for path in artifacts
        ],
    )
    assert all(record.signature_state == "VERIFIED" for record in bundle.integrity_records)
    assert bundle.provenance.required_signature_state == "VERIFIED"


def test_overclaimed_target_coverage_is_rejected(artifacts: tuple[Path, ...]) -> None:
    """A dependency-only report must not be able to claim container coverage."""

    payload = {
        "SchemaVersion": 2,
        "ArtifactName": ".",
        "ArtifactType": "filesystem",
        "Results": [
            {"Target": "uv.lock", "Class": "lang-pkgs", "Type": "uv", "Vulnerabilities": []}
        ],
    }
    with pytest.raises(CandidateEvidenceError):
        _build(artifacts, scanner_runs=(_scanner_run(payload=payload),))


def test_partial_target_coverage_is_rejected(artifacts: tuple[Path, ...]) -> None:
    """Declaring fewer classes than required must not pass."""

    bundle = _build(artifacts, scanner_runs=(_scanner_run(target_classes=("source",)),))
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is not PreAdmissionState.PASS


def test_failed_scan_is_rejected(artifacts: tuple[Path, ...]) -> None:
    bundle = _build(artifacts, scanner_runs=(_scanner_run(execution_state="FAILED"),))
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is not PreAdmissionState.PASS


def test_stale_scan_is_rejected(artifacts: tuple[Path, ...]) -> None:
    stale = datetime.now(UTC) - timedelta(days=3)
    bundle = _build(artifacts, scanner_runs=(_scanner_run(observed_at_utc=stale),))
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT, bundle.evidence)
    assert verdict.state is not PreAdmissionState.PASS


def test_naive_timestamps_are_rejected(artifacts: tuple[Path, ...]) -> None:
    with pytest.raises(CandidateEvidenceError):
        _build(artifacts, now_utc=datetime(2026, 1, 1, 0, 0, 0))
    with pytest.raises(CandidateEvidenceError):
        _build(
            artifacts,
            scanner_runs=(_scanner_run(observed_at_utc=datetime(2026, 1, 1, 0, 0, 0)),),
        )


def test_tampered_artifact_bytes_are_rejected(artifacts: tuple[Path, ...]) -> None:
    bundle = _build(artifacts, scanner_runs=(_scanner_run(),))
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


def test_duplicate_artifacts_are_rejected(artifacts: tuple[Path, ...]) -> None:
    with pytest.raises(CandidateEvidenceError):
        _build(artifacts, artifact_paths=(artifacts[0], artifacts[0]))


def test_no_artifacts_fails_closed() -> None:
    with pytest.raises(CandidateEvidenceError):
        build_candidate_release_evidence(
            REPO_ROOT,
            artifact_paths=(),
            builder_identity_id="actor:test",
        )


def test_unsupported_scanner_is_rejected(artifacts: tuple[Path, ...]) -> None:
    with pytest.raises(CandidateEvidenceError):
        _build(artifacts, scanner_runs=(_scanner_run(tool="not-a-governed-scanner"),))


def test_evidence_is_json_serializable(artifacts: tuple[Path, ...]) -> None:
    bundle = _build(artifacts, scanner_runs=(_scanner_run(),))
    json.dumps(bundle.provenance.model_dump(mode="json"))
