from __future__ import annotations

import json
from pathlib import Path


def load_aws_blueprint(root: Path) -> dict[str, object]:
    policy = json.loads((root / "config/resilience_policy.json").read_text(encoding="utf-8"))
    return dict(policy["aws_cloud_spine"])


def aws_safety_plan(root: Path) -> dict[str, object]:
    blueprint = load_aws_blueprint(root)
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
        "terraform_path": "infrastructure/aws/terraform",
        "live_cloud_mutation_performed": False,
        "activation_preconditions": blueprint["activation_preconditions"],
    }
