from pathlib import Path

from project_pipeline.verification.validation import validate_verification_harness


def test_verification_foundation_is_registered(project_root: Path):
    assert validate_verification_harness(project_root) == []
