from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.assurance.policy import AssurancePolicy

_REQUIRED = (
    "src/project_pipeline/domain/assurance.py",
    "src/project_pipeline/assurance/compiler.py",
    "src/project_pipeline/assurance/completion.py",
    "src/project_pipeline/assurance/evidence.py",
    "src/project_pipeline/assurance/loop_guard.py",
    "src/project_pipeline/assurance/persistence.py",
    "src/project_pipeline/assurance/scope.py",
    "config/assurance_policy.json",
    "provenance/pass_15_verification_gate.json",
    "database/migrations/sqlite/PPDB-0012_execution_assurance_completion_gate.up.sql",
    "database/migrations/postgresql/PPDB-0012_execution_assurance_completion_gate.up.sql",
    "runbooks/completion_failure_rework.md",
    "docs/assurance/completion_gate.md",
    "docs/assurance/execution_assurance.md",
    "plans/08_execution_assurance_and_testing/PLAN-ASSURE-002_execution_assurance_completion_gate_implementation.md",
)


def validate_assurance(root: Path) -> list[str]:
    errors = []
    for rel in _REQUIRED:
        if not (root / rel).exists():
            errors.append(f"assurance required path missing: {rel}")
    policy_path = root / "config/assurance_policy.json"
    if policy_path.exists():
        try:
            AssurancePolicy.model_validate(json.loads(policy_path.read_text(encoding="utf-8")))
        except Exception as exc:
            errors.append(f"assurance policy invalid: {exc}")
    gate_path = root / "provenance/upstream_adoption_gate.json"
    if gate_path.exists():
        gate = (
            json.loads(gate_path.read_text(encoding="utf-8"))
            .get("subsystems", {})
            .get("verification_and_evaluation", {})
        )
        if gate.get("review_state") != "INTEGRATED":
            errors.append("verification/evaluation upstream gate is not INTEGRATED")
        expected = {
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
        if set(gate.get("candidate_upstream_ids", ())) != expected:
            errors.append("verification/evaluation upstream candidate set drifted")
    proof = root / "provenance/pass_15_verification_gate.json"
    if proof.exists():
        data = json.loads(proof.read_text(encoding="utf-8"))
        if data.get("status") != "INTEGRATED" or not data.get("material_implementation_allowed"):
            errors.append(
                "Pass 15 upstream proof does not permit material assurance implementation"
            )

    catalog_path = root / "database/MIGRATION_CATALOG.json"
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        ids = [item.get("migration_id") for item in catalog.get("migrations", ())]
        if "PPDB-0012" not in ids:
            errors.append("PPDB-0012 migration is not current in the migration catalog")
    return errors
