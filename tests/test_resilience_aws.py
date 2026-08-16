from project_pipeline.resilience.aws import aws_safety_plan


def test_aws_blueprint_keeps_local_primary(project_root):
    p = aws_safety_plan(project_root)
    assert p["primary_control_location"] == "LOCAL"
    assert not p["cloud_worker_canonical_authority"]
    assert p["local_state_survives_cloud_removal"]
    assert not p["live_cloud_mutation_performed"]


def test_terraform_is_disabled_by_default(project_root):
    text = (project_root / "infrastructure/aws/terraform/variables.tf").read_text()
    assert "default = false" in text
