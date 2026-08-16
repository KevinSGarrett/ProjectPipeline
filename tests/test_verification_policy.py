from pathlib import Path

from project_pipeline.domain.verification import VerificationCategory
from project_pipeline.verification.harness import default_check_specs
from project_pipeline.verification.policy import load_verification_policy


def test_verification_policy_has_full_pass16_category_portfolio(project_root: Path):
    policy = load_verification_policy(project_root)
    expected = set(VerificationCategory)
    assert set(policy.required_categories) == expected


def test_default_check_specs_cover_every_required_category(project_root: Path):
    policy = load_verification_policy(project_root)
    categories = {item.category for item in default_check_specs()}
    assert set(policy.required_categories) <= categories


def test_required_specs_are_never_preconfigured_as_skip():
    assert all(item.required for item in default_check_specs())
