from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from project_pipeline.domain.resilience import FailureDomain
from project_pipeline.resilience.failover import decide_operating_mode

SECRET_SHAPED = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"
    r"|sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}"
)
SENSITIVE_KEY = re.compile(r"(?i)(api[_-]?key|access[_-]?key|secret|password|token|authorization)$")
ACCOUNT_ID = re.compile(r"^\d{12}$")
ALLOWED_REGIONS = frozenset(
    {
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "eu-west-1",
        "eu-central-1",
    }
)
PHASES = ("PLAN", "APPLY", "DESTROY")
REQUIRED_BLUEPRINT_KEYS = ("services", "credential_policy", "activation_preconditions")


def contains_secret_shaped(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            SENSITIVE_KEY.search(str(key)) or contains_secret_shaped(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret_shaped(item) for item in value)
    return isinstance(value, str) and bool(SECRET_SHAPED.search(value))


def load_aws_blueprint(root: Path) -> dict[str, object]:
    policy = json.loads((root / "config/resilience_policy.json").read_text(encoding="utf-8"))
    return dict(policy["aws_cloud_spine"])


def validate_aws_blueprint(blueprint: dict[str, object]) -> None:
    if contains_secret_shaped(blueprint):
        raise ValueError("aws blueprint contains nested secret-shaped values")
    for key in REQUIRED_BLUEPRINT_KEYS:
        if key not in blueprint:
            raise ValueError(f"aws_cloud_spine missing required key: {key}")
    if str(blueprint.get("primary_control_location", "LOCAL")).upper() != "LOCAL":
        raise ValueError("aws blueprint must keep local-primary authority")
    if blueprint.get("burst_workers_canonical_authority") is True:
        raise ValueError("cloud burst workers cannot hold canonical authority")
    policy_text = str(blueprint["credential_policy"]).lower()
    forbidden_tokens = ("access_key", "secret_key", "password", "token=")
    if any(token in policy_text for token in forbidden_tokens):
        raise ValueError("credential policy must not embed secret-like values")


def validate_activation(activation: dict[str, Any]) -> dict[str, Any]:
    if contains_secret_shaped(activation):
        raise ValueError("activation payload contains nested secret-shaped values")
    account = str(activation.get("account_id", "")).strip()
    region = str(activation.get("region", "")).strip()
    if not ACCOUNT_ID.match(account):
        raise ValueError("invalid AWS account id")
    if region not in ALLOWED_REGIONS:
        raise ValueError("invalid or unapproved AWS region")
    if not activation.get("backend_locking"):
        raise ValueError("state backend locking is required")
    if not activation.get("encryption"):
        raise ValueError("encryption is required")
    if int(activation.get("monthly_budget_usd") or 0) <= 0:
        raise ValueError("budget is required")
    statements = activation.get("iam_statements") or []
    if _has_wildcard_policy(statements):
        raise ValueError("wildcard IAM policy is denied")
    if not activation.get("lease_fencing"):
        raise ValueError("conditional lease fencing is required")
    return {
        "account_id": account,
        "region": region,
        "backend_locking": True,
        "encryption": True,
        "monthly_budget_usd": int(activation["monthly_budget_usd"]),
        "lease_fencing": True,
        "local_primary": True,
    }


def _has_wildcard_policy(statements: Any) -> bool:
    if isinstance(statements, str):
        return "*" in statements and (
            "Action" in statements or "action" in statements or statements.strip() == "*"
        )
    if isinstance(statements, dict):
        action = statements.get("Action") or statements.get("action")
        resource = statements.get("Resource") or statements.get("resource")
        if action == "*" or resource == "*":
            return True
        return any(_has_wildcard_policy(value) for value in statements.values())
    if isinstance(statements, (list, tuple)):
        return any(_has_wildcard_policy(item) for item in statements)
    return False


def terraform_execution_contract(terraform_root: str) -> dict[str, Any]:
    return {
        "terraform_root": terraform_root,
        "plan_required_before_apply": True,
        "apply_requires_explicit_authorization": True,
        "apply_default_mode": "DENY",
        "destroy_default_mode": "DENY",
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
        "non_secret_outputs_only": True,
    }


def plan_identity(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AwsBlueprintGovernor:
    """Separates plan/apply/destroy and reconciles unknown cloud outcomes."""

    def __init__(self) -> None:
        self._plans: dict[str, dict[str, Any]] = {}
        self._outcomes: dict[str, str] = {}

    def record_plan(
        self, activation: dict[str, Any], blueprint: dict[str, object]
    ) -> dict[str, Any]:
        validate_aws_blueprint(blueprint)
        validated = validate_activation(activation)
        payload = {
            "phase": "PLAN",
            "activation": validated,
            "primary_control_location": "LOCAL",
            "enable_cloud_spine": False,
        }
        identity = plan_identity(payload)
        record = {"plan_id": identity, "state": "PLANNED", **payload}
        self._plans[identity] = record
        self._outcomes[identity] = "PLANNED"
        return record

    def transition(
        self,
        plan_id: str,
        phase: str,
        *,
        authorized: bool = False,
        qualified: bool = False,
    ) -> dict[str, Any]:
        if phase not in PHASES:
            raise ValueError(f"unsupported terraform phase: {phase}")
        record = self._plans.get(plan_id)
        if record is None:
            raise KeyError(f"unknown plan: {plan_id}")
        if phase in {"APPLY", "DESTROY"}:
            if not authorized:
                raise ValueError(f"{phase.lower()} denied absent authority")
            if not qualified:
                raise ValueError("unqualified phase transition is denied")
            if self._outcomes.get(plan_id) == "UNKNOWN_OUTCOME":
                raise ValueError("reconcile unknown outcome before retry")
        if phase == "PLAN":
            state = "PLANNED"
        elif phase == "APPLY":
            state = "APPLIED"
        else:
            state = "DESTROYED"
        self._outcomes[plan_id] = state
        return {"plan_id": plan_id, "phase": phase, "state": state}

    def mark_unknown(self, plan_id: str) -> dict[str, Any]:
        if plan_id not in self._plans:
            raise KeyError(f"unknown plan: {plan_id}")
        self._outcomes[plan_id] = "UNKNOWN_OUTCOME"
        return {"plan_id": plan_id, "state": "UNKNOWN_OUTCOME"}

    def reconcile(self, plan_id: str, *, observed_state: str) -> dict[str, Any]:
        if plan_id not in self._plans:
            raise KeyError(f"unknown plan: {plan_id}")
        if observed_state not in {"PLANNED", "APPLIED", "DESTROYED", "ABSENT"}:
            raise ValueError("invalid observed terraform state")
        state = "RECONCILED" if observed_state != "ABSENT" else "FAILED"
        self._outcomes[plan_id] = state
        return {"plan_id": plan_id, "state": state, "observed_state": observed_state}


def aws_outage_local_continuation() -> dict[str, Any]:
    decision = decide_operating_mode(
        (FailureDomain.CLOUD, FailureDomain.NETWORK),
        canonical_state_available=True,
    )
    return {
        "mode": decision.mode.value,
        "local_continuation": decision.mode.value == "LOCAL_FIRST",
        "optional_cloud_degraded": True,
        "canonical_authority": "LOCAL",
        "allowed_capabilities": list(decision.allowed_capabilities),
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
        "optional_cloud_degraded_mode": "LOCAL_FIRST",
        "lease_fencing_required": True,
    }
