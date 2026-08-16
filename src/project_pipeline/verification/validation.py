from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.verification.policy import load_verification_policy

_REQUIRED = (
    "src/project_pipeline/domain/verification.py",
    "src/project_pipeline/verification/harness.py",
    "src/project_pipeline/verification/browser.py",
    "src/project_pipeline/verification/golden.py",
    "src/project_pipeline/verification/property_checks.py",
    "src/project_pipeline/verification/mutation.py",
    "src/project_pipeline/verification/faults.py",
    "src/project_pipeline/verification/performance.py",
    "src/project_pipeline/verification/post_merge.py",
    "src/project_pipeline/verification/external_tools.py",
    "src/project_pipeline/verification/e2e.py",
    "src/project_pipeline/verification/persistence.py",
    "config/verification_policy.json",
    "provenance/pass_16_verification_activation_gate.json",
    "database/migrations/sqlite/PPDB-0013_verification_harness.up.sql",
    "database/migrations/postgresql/PPDB-0013_verification_harness.up.sql",
    "docs/verification/pass16_verification_harness.md",
    "runbooks/verification_failure_triage.md",
    "config/pass23_e2e_journey_matrix.json",
    "provenance/pass_23_upstream_e2e_gate.json",
    "provenance/reviews/PASS-23_full_e2e_upstream_review.md",
    "docs/verification/pass23_full_end_to_end_integration.md",
    "tests/test_pass23_full_e2e.py",
    "plans/08_execution_assurance_and_testing/PLAN-VERIFY-001_verification_harness_golden_journeys.md",
)

_EXPECTED_UPSTREAM = {
    "UPSTREAM-015",
    "UPSTREAM-027",
    "UPSTREAM-032",
    "UPSTREAM-044",
    "UPSTREAM-051",
    "UPSTREAM-063",
    "UPSTREAM-064",
    "UPSTREAM-085",
    "UPSTREAM-092",
    "UPSTREAM-093",
    "UPSTREAM-101",
    "UPSTREAM-108",
    "UPSTREAM-111",
}


def validate_verification_harness(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in _REQUIRED:
        if not (root / relative).exists():
            errors.append(f"verification required path missing: {relative}")
    try:
        policy = load_verification_policy(root)
        required = {item.value for item in policy.required_categories}
        expected = {
            "CONTRACT",
            "API",
            "INTEGRATION",
            "END_TO_END",
            "GOLDEN_JOURNEY",
            "ADVERSARIAL",
            "PROPERTY",
            "MUTATION",
            "FAULT",
            "POST_MERGE",
        }
        if not expected.issubset(required):
            errors.append("verification policy is missing required Pass 16 categories")
    except Exception as exc:
        errors.append(f"verification policy invalid: {exc}")

    gate_path = root / "provenance" / "pass_16_verification_activation_gate.json"
    if gate_path.exists():
        try:
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            if gate.get("status") != "INTEGRATED" or not gate.get(
                "material_implementation_allowed"
            ):
                errors.append("Pass 16 activation gate is not integrated/open")
            if set(gate.get("candidate_upstream_ids", ())) != _EXPECTED_UPSTREAM:
                errors.append("Pass 16 activation candidate set drifted")
            if gate.get("correction_rounds_repeated"):
                errors.append("Pass 16 incorrectly repeated the historical corrective program")
        except Exception as exc:
            errors.append(f"Pass 16 activation gate invalid: {exc}")

    adoption = root / "provenance" / "upstream_adoption_gate.json"
    if adoption.exists():
        document = json.loads(adoption.read_text(encoding="utf-8"))
        subsystem = document.get("subsystems", {}).get("verification_and_evaluation", {})
        if subsystem.get("review_state") != "INTEGRATED":
            errors.append("verification/evaluation upstream subsystem is not integrated")
        if set(subsystem.get("candidate_upstream_ids", ())) != _EXPECTED_UPSTREAM:
            errors.append("verification/evaluation candidate set drifted")

    pass23_gate = root / "provenance" / "pass_23_upstream_e2e_gate.json"
    if pass23_gate.exists():
        try:
            gate = json.loads(pass23_gate.read_text(encoding="utf-8"))
            expected = {
                "UPSTREAM-011",
                "UPSTREAM-041",
                "UPSTREAM-050",
                "UPSTREAM-063",
                "UPSTREAM-086",
                "UPSTREAM-092",
                "UPSTREAM-093",
                "UPSTREAM-102",
                "UPSTREAM-105",
            }
            if gate.get("status") != "INTEGRATED" or not gate.get(
                "material_implementation_allowed"
            ):
                errors.append("Pass 23 E2E upstream gate is not integrated/open")
            if set(gate.get("candidate_upstream_ids", ())) != expected:
                errors.append("Pass 23 E2E upstream candidate set drifted")
            if gate.get("live_external_mutation_performed"):
                errors.append("Pass 23 gate falsely claims live external mutation")
        except Exception as exc:
            errors.append(f"Pass 23 E2E upstream gate invalid: {exc}")

    matrix_path = root / "config" / "pass23_e2e_journey_matrix.json"
    if matrix_path.exists():
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            names = {item.get("name") for item in matrix.get("journeys", ())}
            if names != {
                "full_project_pipeline_journey",
                "duplicate_and_idempotency",
                "partial_failure_retry_and_recovery",
            }:
                errors.append("Pass 23 E2E journey matrix drifted")
            for item in matrix.get("journeys", ()):
                for field in (
                    "environment",
                    "setup",
                    "actions",
                    "observable_result",
                    "cleanup",
                    "preserved_evidence",
                ):
                    if not item.get(field):
                        errors.append(f"Pass 23 journey {item.get('journey_id')} lacks {field}")
        except Exception as exc:
            errors.append(f"Pass 23 E2E journey matrix invalid: {exc}")

    catalog = root / "database" / "MIGRATION_CATALOG.json"
    if catalog.exists():
        data = json.loads(catalog.read_text(encoding="utf-8"))
        if "PPDB-0013" not in {item.get("migration_id") for item in data.get("migrations", ())}:
            errors.append("PPDB-0013 is missing from migration catalog")
    return errors
