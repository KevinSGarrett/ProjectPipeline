from pathlib import Path

from project_pipeline.assurance.validation import validate_assurance


def test_assurance_foundation_contract_is_present():
    assert validate_assurance(Path.cwd()) == []
