import pytest

from project_pipeline.resilience.aws import (
    AwsBlueprintGovernor,
    aws_outage_local_continuation,
    aws_safety_plan,
    contains_secret_shaped,
    load_aws_blueprint,
    validate_activation,
    validate_aws_blueprint,
)


def _activation(**overrides):
    payload = {
        "account_id": "123456789012",
        "region": "us-east-1",
        "backend_locking": True,
        "encryption": True,
        "monthly_budget_usd": 25,
        "lease_fencing": True,
        "iam_statements": [{"Action": "s3:GetObject", "Resource": "arn:aws:s3:::bucket/object"}],
    }
    payload.update(overrides)
    return payload


def test_aws_blueprint_keeps_local_primary(project_root):
    p = aws_safety_plan(project_root)
    assert p["primary_control_location"] == "LOCAL"
    assert not p["cloud_worker_canonical_authority"]
    assert p["local_state_survives_cloud_removal"]
    assert not p["live_cloud_mutation_performed"]
    assert p["account_region_authority_gate_required"]
    assert p["mock_local_live_evidence_distinction_required"]
    assert p["optional_cloud_degraded_mode"] == "LOCAL_FIRST"
    contract = p["terraform_execution_contract"]
    assert contract["plan_required_before_apply"]
    assert contract["apply_default_mode"] == "DENY"
    assert contract["destroy_default_mode"] == "DENY"
    assert "terraform apply" in contract["blocked_commands_without_explicit_gate"]


def test_terraform_is_disabled_by_default(project_root):
    text = (project_root / "infrastructure/aws/terraform/variables.tf").read_text()
    assert 'variable "enable_cloud_spine"' in text
    assert "default     = false" in text or "default = false" in text
    assert "enable_budget_circuit_breaker" in text


def test_nested_secret_and_wildcard_policy_are_rejected(project_root):
    blueprint = load_aws_blueprint(project_root)
    assert contains_secret_shaped(blueprint) is False
    validate_aws_blueprint(blueprint)
    nested = dict(blueprint)
    nested["nested"] = {"password": "hunter2"}
    with pytest.raises(ValueError, match="secret-shaped"):
        validate_aws_blueprint(nested)
    with pytest.raises(ValueError, match="wildcard"):
        validate_activation(_activation(iam_statements=[{"Action": "*", "Resource": "*"}]))
    with pytest.raises(ValueError, match="account"):
        validate_activation(_activation(account_id="not-an-account"))
    with pytest.raises(ValueError, match="region"):
        validate_activation(_activation(region="mars-1"))
    with pytest.raises(ValueError, match="locking"):
        validate_activation(_activation(backend_locking=False))
    with pytest.raises(ValueError, match="encryption"):
        validate_activation(_activation(encryption=False))
    with pytest.raises(ValueError, match="budget"):
        validate_activation(_activation(monthly_budget_usd=0))


def test_plan_apply_destroy_require_authority_and_reconcile_unknown(project_root):
    governor = AwsBlueprintGovernor()
    planned = governor.record_plan(_activation(), load_aws_blueprint(project_root))
    with pytest.raises(ValueError, match="denied"):
        governor.transition(planned["plan_id"], "APPLY", authorized=False, qualified=True)
    with pytest.raises(ValueError, match="unqualified"):
        governor.transition(planned["plan_id"], "APPLY", authorized=True, qualified=False)
    with pytest.raises(ValueError, match="denied"):
        governor.transition(planned["plan_id"], "DESTROY", authorized=False, qualified=True)
    applied = governor.transition(planned["plan_id"], "APPLY", authorized=True, qualified=True)
    assert applied["state"] == "APPLIED"
    governor.mark_unknown(planned["plan_id"])
    with pytest.raises(ValueError, match="unknown outcome"):
        governor.transition(planned["plan_id"], "DESTROY", authorized=True, qualified=True)
    reconciled = governor.reconcile(planned["plan_id"], observed_state="APPLIED")
    assert reconciled["state"] == "RECONCILED"


def test_aws_outage_continues_local_first():
    result = aws_outage_local_continuation()
    assert result["local_continuation"] is True
    assert result["mode"] == "LOCAL_FIRST"
    assert result["canonical_authority"] == "LOCAL"
