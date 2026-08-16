from __future__ import annotations

import json
from pathlib import Path

_REQUIRED = (
    "src/project_pipeline/convergence/audit.py",
    "src/project_pipeline/convergence/validation.py",
    "release/final_convergence_audit_r25.json",
    "docs/release/FINAL_CONVERGENCE_HANDOFF.md",
    "database/migrations/sqlite/PPDB-0019_audit_immutability.up.sql",
    "database/migrations/postgresql/PPDB-0019_audit_immutability.up.sql",
    "config/runbooks/recovery_control_machine.json",
)


def validate_final_convergence(root: Path) -> list[str]:
    errors = []
    for rel in _REQUIRED:
        if not (root / rel).exists():
            errors.append(f"final convergence required path missing: {rel}")
    report = root / "release/final_convergence_audit_r25.json"
    if report.exists():
        try:
            saved = json.loads(report.read_text(encoding="utf-8"))
            if saved.get("audit_id") != "PASS-25-FINAL-CONVERGENCE-AUDIT":
                errors.append("final convergence audit id drifted")
            if saved.get("truth_boundary") is None:
                errors.append("final convergence truth boundary missing")
            if saved.get("accepted_requirement_count") != 351:
                errors.append("final convergence accepted requirement coverage is incomplete")
        except Exception as exc:
            errors.append(f"final convergence report invalid: {exc}")
    return errors
