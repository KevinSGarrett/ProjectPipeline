from project_pipeline.resilience.aws import aws_safety_plan


def test_aws_blueprint_keeps_local_primary(project_root):
    p = aws_safety_plan(project_root)
    assert p["primary_control_location"] == "LOCAL"
    assert not p["cloud_worker_canonical_authority"]
    assert p["local_state_survives_cloud_removal"]
    assert not p["live_cloud_mutation_performed"]
    assert p["account_region_authority_gate_required"]
    assert p["mock_local_live_evidence_distinction_required"]
    contract = p["terraform_execution_contract"]
    assert contract["plan_required_before_apply"]
    assert contract["apply_default_mode"] == "DENY"
    assert "terraform apply" in contract["blocked_commands_without_explicit_gate"]


def test_terraform_is_disabled_by_default(project_root):
    text = (project_root / "infrastructure/aws/terraform/variables.tf").read_text()
    assert "variable \"enable_cloud_spine\"" in text
    assert "default     = false" in text or "default = false" in text
