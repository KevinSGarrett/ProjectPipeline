from project_pipeline.domain.verification import VerificationCategory
from project_pipeline.verification.impact import derive_test_impact


def test_budget_change_derives_integration_fault_and_contract_verification():
    impact = derive_test_impact(["src/project_pipeline/budget/governor.py"])
    assert VerificationCategory.INTEGRATION in impact.required_categories
    assert VerificationCategory.FAULT in impact.required_categories
    assert VerificationCategory.CONTRACT in impact.required_categories


def test_ui_change_derives_browser_accessibility_performance_and_end_to_end():
    impact = derive_test_impact(["src/project_pipeline/command_center/app.py"])
    assert {
        VerificationCategory.END_TO_END,
        VerificationCategory.BROWSER,
        VerificationCategory.VISUAL,
        VerificationCategory.ACCESSIBILITY,
        VerificationCategory.PERFORMANCE,
    }.issubset(set(impact.required_categories))


def test_unclassified_change_fails_safe_instead_of_skipping_verification():
    impact = derive_test_impact(["README.md"])
    assert impact.required_categories == (
        VerificationCategory.CONTRACT,
        VerificationCategory.POST_MERGE,
    )


def test_test_impact_identity_is_deterministic_across_path_order():
    left = derive_test_impact(
        ["src/project_pipeline/budget/governor.py", "schemas/example.json"],
        requirement_ids=["REQ-BUDGET-0001"],
    )
    right = derive_test_impact(
        ["schemas/example.json", "src/project_pipeline/budget/governor.py"],
        requirement_ids=["REQ-BUDGET-0001"],
    )
    assert left.impact_id == right.impact_id


def test_critical_risk_and_acceptance_methods_broaden_impact_set():
    impact = derive_test_impact(
        ["src/project_pipeline/control/kernel.py"],
        dependency_paths=["src/project_pipeline/orchestration/service.py"],
        risk="CRITICAL",
        acceptance_methods=["browser accessibility", "fault recovery"],
    )
    assert {
        VerificationCategory.ADVERSARIAL,
        VerificationCategory.PROPERTY,
        VerificationCategory.GOLDEN_JOURNEY,
        VerificationCategory.END_TO_END,
        VerificationCategory.FAULT,
        VerificationCategory.BROWSER,
        VerificationCategory.VISUAL,
        VerificationCategory.ACCESSIBILITY,
        VerificationCategory.INTEGRATION,
    }.issubset(set(impact.required_categories))
