from project_pipeline.resilience.validation import validate_resilience_foundation


def test_resilience_foundation_is_coherent(project_root):
    assert validate_resilience_foundation(project_root) == []
