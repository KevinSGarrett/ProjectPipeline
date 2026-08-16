from pathlib import Path

from project_pipeline.verification.adversarial import run_adversarial_checks


def test_adversarial_invariants_reject_unsafe_inputs(project_root: Path):
    observations = run_adversarial_checks(project_root)
    assert "required-check-silent-skip rejected" in observations
    assert "single-false-completion-fact prevents completion" in observations
    assert "api-schema-path-traversal rejected" in observations
    assert "external-axe-bundle rejected" in observations
