from project_pipeline.security.validation import validate_security_foundation


def test_security_foundation_contract(project_root):
    errors = validate_security_foundation(project_root)
    assert errors == []
