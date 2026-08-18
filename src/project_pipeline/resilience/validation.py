from __future__ import annotations

import json
from pathlib import Path

_REQUIRED = (
    "src/project_pipeline/domain/resilience.py",
    "src/project_pipeline/resilience/failover.py",
    "src/project_pipeline/resilience/local_models.py",
    "src/project_pipeline/resilience/backup.py",
    "src/project_pipeline/resilience/aws.py",
    "src/project_pipeline/resilience/persistence.py",
    "src/project_pipeline/resilience/runbook.py",
    "src/project_pipeline/resilience/simulation.py",
    "config/resilience_policy.json",
    "database/migrations/sqlite/PPDB-0015_resilience_recovery_local_runtime.up.sql",
    "database/migrations/postgresql/PPDB-0015_resilience_recovery_local_runtime.up.sql",
    "docs/operations/resilience_and_recovery.md",
    "runbooks/backup_restore_verification.md",
    "runbooks/control_machine_failover.md",
    "runbooks/external_precondition_recovery.md",
    "config/runbooks/recovery_control_machine.json",
    "infrastructure/aws/terraform/main.tf",
    "infrastructure/aws/terraform/variables.tf",
)
_EXPECTED = {
    "UPSTREAM-040",
    "UPSTREAM-058",
    "UPSTREAM-068",
    "UPSTREAM-072",
    "UPSTREAM-082",
    "UPSTREAM-090",
    "UPSTREAM-093",
}


def validate_resilience_foundation(root: Path) -> list[str]:
    errors = []
    for rel in _REQUIRED:
        if not (root / rel).exists():
            errors.append(f"resilience required path missing: {rel}")
    try:
        policy = json.loads((root / "config/resilience_policy.json").read_text(encoding="utf-8"))
        if set(policy.get("operating_modes", ())) != {
            "FULL",
            "DEGRADED",
            "LOCAL_FIRST",
            "RECOVERY",
            "PAUSED",
            "EMERGENCY_STOP",
        }:
            errors.append("operating mode set drifted")
        if not policy.get("recovery_objectives"):
            errors.append("recovery objectives are missing")
        if policy.get("deterministic_control_authority") != "PROJECT_PIPELINE":
            errors.append("deterministic control authority drifted")
        if policy.get("aws_cloud_spine", {}).get("primary_control_location") != "LOCAL":
            errors.append("AWS blueprint moved primary control authority")
    except Exception as exc:
        errors.append(f"resilience policy invalid: {exc}")
    try:
        rows = [
            json.loads(x)
            for x in (root / "provenance/upstream_usage.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if x.strip()
        ]
        selected = {
            x["upstream_id"]
            for x in rows
            if x.get("upstream_id") in _EXPECTED
            and x.get("usage_state")
            in {"OPTIONAL_ADAPTER_IMPLEMENTED", "IMPLEMENTATION_PATTERN_ADOPTED"}
        }
        if selected != _EXPECTED:
            errors.append(
                f"resilience upstream integration set incomplete: {sorted(_EXPECTED - selected)}"
            )
    except Exception as exc:
        errors.append(f"upstream usage invalid: {exc}")
    try:
        catalog = json.loads((root / "database/MIGRATION_CATALOG.json").read_text(encoding="utf-8"))
        if "PPDB-0015" not in {x.get("migration_id") for x in catalog.get("migrations", ())}:
            errors.append("PPDB-0015 missing from migration catalog")
    except Exception as exc:
        errors.append(f"migration catalog invalid: {exc}")
    return errors
