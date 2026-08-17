from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_aws_blueprint(root: Path) -> dict[str, object]:
    policy = json.loads((root / "config/resilience_policy.json").read_text(encoding="utf-8"))
    return dict(policy["aws_cloud_spine"])


def validate_aws_blueprint(blueprint: dict[str, object]) -> None:
    for key in ("services", "credential_policy", "activation_preconditions"):
        if key not in blueprint:
            raise ValueError(f"aws_cloud_spine missing required key: {key}")
    policy_text = str(blueprint["credential_policy"]).lower()
    forbidden_tokens = ("access_key", "secret_key", "password", "token=")
    if any(token in policy_text for token in forbidden_tokens):
        raise ValueError("credential policy must not embed secret-like values")


def terraform_execution_contract(terraform_root: str) -> dict[str, Any]:
    return {
        "terraform_root": terraform_root,
        "plan_required_before_apply": True,
        "apply_requires_explicit_authorization": True,
        "apply_default_mode": "DENY",
        "supports_state_locking": True,
        "supports_drift_detection": True,
        "supports_partial_create_recovery": True,
        "supports_unknown_outcome_reconcile_before_retry": True,
        "supports_fail_closed_teardown": True,
        "live_mutation_performed": False,
        "safe_commands": {
            "fmt": ["terraform", "fmt", "-check"],
            "validate": ["terraform", "validate"],
            "plan": ["terraform", "plan", "-lock=true", "-input=false"],
        },
        "blocked_commands_without_explicit_gate": [
            "terraform apply",
            "terraform destroy",
        ],
    }


def aws_safety_plan(root: Path) -> dict[str, object]:
    blueprint = load_aws_blueprint(root)
    validate_aws_blueprint(blueprint)
    terraform_root = "infrastructure/aws/terraform"
    return {
        "profile": "LOCAL_PRIMARY_HYBRID_AWS",
        "primary_control_location": "LOCAL",
        "cloud_control_authority": "WITNESS_AND_OPTIONAL_RECOVERY_ONLY",
        "services": blueprint["services"],
        "credential_policy": blueprint["credential_policy"],
        "budget_gate_required": True,
        "external_budget_circuit_breaker_source_implemented": True,
        "external_budget_circuit_breaker_live_verified": False,
        "cloud_worker_canonical_authority": False,
        "local_state_survives_cloud_removal": True,
        "terraform_path": terraform_root,
        "terraform_execution_contract": terraform_execution_contract(terraform_root),
        "live_cloud_mutation_performed": False,
        "mock_local_live_evidence_distinction_required": True,
        "account_region_authority_gate_required": True,
        "cost_gate_required_before_live_apply": True,
        "activation_preconditions": blueprint["activation_preconditions"],
    }
