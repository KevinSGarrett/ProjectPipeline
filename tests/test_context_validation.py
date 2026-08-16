from project_pipeline.context_engine import validate_context_foundation


def test_context_foundation_is_registered_and_valid(project_root):
    assert validate_context_foundation(project_root) == []
