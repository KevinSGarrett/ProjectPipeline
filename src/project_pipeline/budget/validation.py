from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.domain.budget import BudgetPolicy
from project_pipeline.upstream import IMPLEMENTED_USAGE_STATES, load_upstream_usage

_REQUIRED_PATHS = (
    "src/project_pipeline/domain/budget.py",
    "src/project_pipeline/budget/persistence.py",
    "src/project_pipeline/budget/policy.py",
    "src/project_pipeline/budget/service.py",
    "src/project_pipeline/budget/forecast.py",
    "src/project_pipeline/budget/infracost.py",
    "src/project_pipeline/budget/integration.py",
    "src/project_pipeline/budget/simulation.py",
    "database/migrations/sqlite/PPDB-0011_budget_governor.up.sql",
    "database/migrations/sqlite/PPDB-0011_budget_governor.down.sql",
    "database/migrations/postgresql/PPDB-0011_budget_governor.up.sql",
    "database/migrations/postgresql/PPDB-0011_budget_governor.down.sql",
    "provenance/pass_14_budget_gate.json",
    "provenance/reviews/PASS-14_budget_upstream_review.md",
    "config/budget_policy.json",
)
_EXPECTED_UPSTREAM = {
    "UPSTREAM-012": "OPTIONAL_ADAPTER_IMPLEMENTED",
    "UPSTREAM-053": "EXTERNAL_CLI_ADAPTER_IMPLEMENTED",
    "UPSTREAM-059": "ARCHITECTURE_PATTERN_ADOPTED",
    "UPSTREAM-065": "IMPLEMENTATION_PATTERN_ADOPTED",
    "UPSTREAM-077": "OPTIONAL_ADAPTER_IMPLEMENTED",
}


def validate_budget_foundation(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in _REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"budget foundation path is missing: {relative}")
    gate_path = root / "provenance" / "pass_14_budget_gate.json"
    if gate_path.exists():
        try:
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            errors.append(f"Pass 14 budget gate is invalid JSON: {error}")
        else:
            if gate.get("candidate_count") != 5:
                errors.append("Pass 14 budget gate candidate count is not 5")
            if set(gate.get("candidate_upstream_ids", [])) != set(_EXPECTED_UPSTREAM):
                errors.append("Pass 14 budget gate candidate set drifted")
            if gate.get("status") != "INTEGRATED":
                errors.append("Pass 14 budget gate is not INTEGRATED")
            if not gate.get("material_implementation_allowed"):
                errors.append(
                    "Pass 14 budget gate did not preserve upstream-first completion evidence"
                )
            if gate.get("budget_authority") != "PROJECT_PIPELINE_DETERMINISTIC":
                errors.append("Budget authority drifted away from Project Pipeline")
            if gate.get("missing_price_semantics") != "UNKNOWN_NOT_ZERO":
                errors.append("Missing budget pricing must remain UNKNOWN_NOT_ZERO")
    policy_path = root / "config" / "budget_policy.json"
    if policy_path.exists():
        try:
            BudgetPolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))
        except Exception as error:
            errors.append(f"budget policy is invalid: {error}")
    usage = {item.get("upstream_id"): item for item in load_upstream_usage(root)}
    for upstream_id, expected in _EXPECTED_UPSTREAM.items():
        record = usage.get(upstream_id)
        if record is None:
            errors.append(f"budget upstream usage record missing: {upstream_id}")
            continue
        if record.get("usage_state") != expected:
            errors.append(
                f"budget upstream {upstream_id} expected {expected}, observed {record.get('usage_state')}"
            )
        if expected in IMPLEMENTED_USAGE_STATES and not record.get("integration_paths"):
            errors.append(f"budget upstream {upstream_id} has no integration paths")
    return errors
