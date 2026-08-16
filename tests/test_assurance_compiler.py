from pathlib import Path

from project_pipeline.assurance.compiler import compile_issue_criteria, compile_repository_plan
from project_pipeline.domain.assurance import VerificationMethod


def _issue():
    return {
        "local_id": "PP-TASK-TEST001",
        "risk_classification": "HIGH",
        "requirement_ids": ["REQ-ASSURE-0014"],
        "acceptance_criteria": [
            {
                "statement": "Compiler output is deterministically verifiable.",
                "verification": {
                    "method": "pytest",
                    "command": "pytest tests/test_assurance_compiler.py",
                },
            },
            {
                "statement": "Unspecified verification remains objectively flagged.",
                "verification": {},
            },
        ],
    }


def test_compile_issue_criteria_is_deterministic():
    first = compile_issue_criteria(_issue())
    second = compile_issue_criteria(_issue())
    assert first == second
    assert first[0].verification_methods == (VerificationMethod.UNIT,)
    assert first[0].objective is True


def test_compile_issue_criteria_marks_missing_verification_non_objective():
    criteria = compile_issue_criteria(_issue())
    assert criteria[1].objective is False
    assert criteria[1].verification_methods == (VerificationMethod.STATIC,)


def test_repository_plan_compiles_real_jira_and_has_stable_fingerprint():
    root = Path.cwd()
    first = compile_repository_plan(root, "PROJECT-PIPELINE")
    second = compile_repository_plan(root, "PROJECT-PIPELINE")
    assert first.fingerprint == second.fingerprint
    assert first.plan_id == second.plan_id
    assert len(first.criteria) > 0
    assert len({c.criterion_id for c in first.criteria}) == len(first.criteria)


def test_repository_plan_rejects_unverifiable_criterion_before_work(monkeypatch, tmp_path):
    invalid = _issue()
    invalid["acceptance_criteria"] = [
        {"statement": "This criterion has no observable verifier.", "verification": {}}
    ]
    monkeypatch.setattr("project_pipeline.assurance.compiler.load_issues", lambda root: [invalid])
    import pytest

    with pytest.raises(ValueError, match="not objectively verifiable"):
        compile_repository_plan(tmp_path, "PROJECT-PIPELINE")
