from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.domain.verification import PostMergeReport, verification_identifier
from project_pipeline.manifest import verify_manifest
from project_pipeline.validation.repository import RepositoryValidator


def evaluate_post_merge(root: Path, *, required_test_suite_ok: bool) -> PostMergeReport:
    manifest_errors = verify_manifest(root)
    validation = RepositoryValidator(root).validate()
    coverage = json.loads(
        (root / "plans/_traceability/coverage_report.json").read_text(encoding="utf-8")
    )
    traceability_ok = int(coverage.get("unexplained_gap_count", coverage.get("gap_count", 0))) == 0
    evidence_summary = json.loads(
        (root / "evidence/EVIDENCE_SUMMARY.json").read_text(encoding="utf-8")
    )
    evidence_integrity_ok = int(evidence_summary.get("verification_failure_count", 0)) == 0
    observations = (
        f"manifest_errors:{len(manifest_errors)}",
        f"repository_errors:{len(validation.errors)}",
        f"repository_warnings:{len(validation.warnings)}",
        f"unexplained_traceability_gaps:{coverage.get('unexplained_gap_count', coverage.get('gap_count', 0))}",
        f"evidence_verification_failures:{evidence_summary.get('verification_failure_count', 0)}",
        f"required_test_suite_ok:{required_test_suite_ok}",
    )
    flags = (
        not manifest_errors,
        validation.ok,
        traceability_ok,
        evidence_integrity_ok,
        required_test_suite_ok,
    )
    return PostMergeReport(
        report_id=verification_identifier("PMERGE", *observations),
        repository_manifest_ok=flags[0],
        repository_validation_ok=flags[1],
        traceability_ok=flags[2],
        evidence_integrity_ok=flags[3],
        required_test_suite_ok=flags[4],
        final_passed=all(flags),
        observations=observations,
    )
