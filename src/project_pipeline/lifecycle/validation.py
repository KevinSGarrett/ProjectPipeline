from __future__ import annotations

import json
from pathlib import Path

_REQUIRED = (
    "src/project_pipeline/domain/lifecycle.py",
    "src/project_pipeline/lifecycle/portfolio.py",
    "src/project_pipeline/lifecycle/repositories.py",
    "src/project_pipeline/lifecycle/environments.py",
    "src/project_pipeline/lifecycle/contracts.py",
    "src/project_pipeline/lifecycle/retention.py",
    "src/project_pipeline/lifecycle/qualification.py",
    "src/project_pipeline/lifecycle/adoption.py",
    "src/project_pipeline/lifecycle/persistence.py",
    "src/project_pipeline/lifecycle/simulation.py",
    "config/platform_lifecycle_policy.json",
    "database/migrations/sqlite/PPDB-0018_advanced_platform_lifecycle.up.sql",
    "database/migrations/postgresql/PPDB-0018_advanced_platform_lifecycle.up.sql",
    "provenance/pass_22_upstream_gate.json",
    "provenance/reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md",
    "docs/lifecycle/advanced_platform_lifecycle.md",
    "runbooks/project_closure_and_archive.md",
    "runbooks/platform_upgrade_qualification.md",
)


def validate_lifecycle_foundation(root: Path) -> list[str]:
    errors = []
    for rel in _REQUIRED:
        if not (root / rel).exists():
            errors.append(f"lifecycle required path missing: {rel}")
    try:
        p = json.loads((root / "config/platform_lifecycle_policy.json").read_text(encoding="utf-8"))
        if p.get("canonical_authority") != "PROJECT_PIPELINE":
            errors.append("lifecycle canonical authority drifted")
        if (
            p.get("destructive_operations", {}).get("retention_expiry_is_deletion_authority")
            is not False
        ):
            errors.append("retention expiry became deletion authority")
        if p.get("test_data", {}).get("production_data_default") != "DENY":
            errors.append("production test-data default must be DENY")
        if p.get("renovate", {}).get("activation") != "PROHIBITED_BY_LICENSE_POLICY":
            errors.append("Renovate license gate drifted")
    except Exception as exc:
        errors.append(f"lifecycle policy invalid: {exc}")
    try:
        gate = json.loads(
            (root / "provenance/pass_22_upstream_gate.json").read_text(encoding="utf-8")
        )
        if gate.get("status") != "INTEGRATED" or not gate.get("material_implementation_allowed"):
            errors.append("Pass 22 upstream gate is not integrated")
        if gate.get("renovate_activation") != "PROHIBITED_BY_LICENSE_POLICY":
            errors.append("Pass 22 gate bypasses Renovate license policy")
    except Exception as exc:
        errors.append(f"Pass 22 gate invalid: {exc}")
    try:
        cat = json.loads((root / "database/MIGRATION_CATALOG.json").read_text(encoding="utf-8"))
        if "PPDB-0018" not in {x.get("migration_id") for x in cat.get("migrations", ())}:
            errors.append("PPDB-0018 missing from migration catalog")
    except Exception as exc:
        errors.append(f"migration catalog invalid: {exc}")
    return errors
