from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.domain.github import AutonomousReviewReceipt, ReviewFinding, github_identifier
from project_pipeline.governance.framework_version import evaluate_framework_version
from project_pipeline.governance.instruction_system import evaluate_instruction_system
from project_pipeline.governance.post_merge_refresh import plan_post_merge_refresh
from project_pipeline.governance.product_profile import evaluate_product_profile
from project_pipeline.governance.review_director import coordinate_independent_review
from project_pipeline.release_hardening.continuation import (
    build_continuation_package,
    evaluate_continuation_freshness,
    validate_continuation_package,
)

ROOT = Path(__file__).resolve().parents[1]


def test_instruction_system_covers_required_modules() -> None:
    verdict = evaluate_instruction_system(ROOT)
    assert verdict["ok"] is True
    assert verdict["user_action_required"] is False
    for module in (
        "governance",
        "git",
        "jira",
        "security",
        "testing",
        "environments",
        "deployment",
        "project_profile",
    ):
        assert verdict["modules"][module]["present"] is True


def test_instruction_system_fails_closed_when_primary_missing(tmp_path: Path) -> None:
    (tmp_path / "instructions").mkdir()
    (tmp_path / "instructions" / "INSTRUCTION_COVERAGE_MATRIX.json").write_text(
        '{"domains": [], "schema_version": "1.0.0"}',
        encoding="utf-8",
    )
    verdict = evaluate_instruction_system(tmp_path)
    assert verdict["ok"] is False
    assert "governance" in verdict["missing_modules"]


def test_review_director_rejects_self_review() -> None:
    now = datetime.now(UTC)
    receipt = AutonomousReviewReceipt(
        receipt_id=github_identifier("GHARV", "test", "self"),
        implementer_id="actor:same",
        reviewer_id="actor:same",
        implementer_context_fingerprint="a" * 64,
        reviewer_context_fingerprint="b" * 64,
        head_sha="a" * 40,
        tree_sha="b" * 40,
        findings=(),
        completed_at_utc=now,
        max_age_seconds=3600,
    )
    verdict = coordinate_independent_review(
        receipt,
        expected_head_sha="a" * 40,
        expected_tree_sha="b" * 40,
        implementer_id="actor:same",
    )
    assert verdict["accepted"] is False
    assert verdict["implemented"] is False
    assert "self_review" in verdict["blockers"]


def test_review_director_accepts_distinct_read_only_reviewer() -> None:
    now = datetime.now(UTC)
    receipt = AutonomousReviewReceipt(
        receipt_id=github_identifier("GHARV", "test", "ok"),
        implementer_id="actor:implementer",
        reviewer_id="actor:reviewer",
        implementer_context_fingerprint="a" * 64,
        reviewer_context_fingerprint="b" * 64,
        head_sha="c" * 40,
        tree_sha="d" * 40,
        findings=(
            ReviewFinding(
                finding_id="FIND-NONE",
                severity="INFO",
                summary="no blocking defect",
                disposition="ACCEPTED",
            ),
        ),
        completed_at_utc=now,
        max_age_seconds=3600,
    )
    verdict = coordinate_independent_review(
        receipt,
        expected_head_sha="c" * 40,
        expected_tree_sha="d" * 40,
        implementer_id="actor:implementer",
    )
    assert verdict["accepted"] is True
    assert verdict["implemented"] is False
    assert verdict["reviewer_authority"] == "READ_ONLY"


def test_framework_version_records_current_catalog() -> None:
    verdict = evaluate_framework_version(ROOT)
    assert verdict["ok"] is True
    assert verdict["observed_latest_database_migration"] == "PPDB-0024"
    assert verdict["recorded_latest_database_migration"] == "PPDB-0024"
    assert verdict["drift"] == []


def test_framework_version_reports_migration_drift(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "database").mkdir()
    (tmp_path / "instructions").mkdir()
    (tmp_path / "config" / "version_compatibility.json").write_text(
        '{"latest_database_migration": "PPDB-0014", "platform_version": "0.9.0", "schema_version": "1.0.0"}',
        encoding="utf-8",
    )
    (tmp_path / "database" / "MIGRATION_CATALOG.json").write_text(
        '{"migrations": [{"migration_id": "PPDB-0024"}]}',
        encoding="utf-8",
    )
    (tmp_path / "instructions" / "INSTRUCTION_MANIFEST.json").write_text("{}", encoding="utf-8")
    verdict = evaluate_framework_version(tmp_path)
    assert verdict["ok"] is False
    assert "database_migration" in verdict["drift"]


def test_product_profile_is_local_first_without_paid_or_chat_dependency() -> None:
    verdict = evaluate_product_profile(ROOT)
    assert verdict["ok"] is True
    assert verdict["local_first"] is True
    assert verdict["paid_service_required_by_default"] is False
    assert verdict["consumer_chat_automation_excluded"] is True


def test_product_profile_rejects_paid_default(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        '{"operating_model": "cloud-first", "paid_service_required_by_default": true}',
        encoding="utf-8",
    )
    verdict = evaluate_product_profile(tmp_path)
    assert verdict["ok"] is False
    assert "paid_service_required_by_default" in verdict["reasons"]
    assert "operating_model_not_local_first" in verdict["reasons"]


def test_continuation_freshness_fails_after_later_merge() -> None:
    package = build_continuation_package(ROOT)
    assert validate_continuation_package(package, reject_stale=False) == []
    stale = dict(package)
    stale["source_sha"] = "0" * 40
    stale["source_tree"] = "1" * 40
    freshness = evaluate_continuation_freshness(
        stale,
        origin_sha=package["source_sha"],
        origin_tree=package["source_tree"],
    )
    assert freshness["stale_after_merge"] is True
    stale["freshness"] = freshness
    errors = validate_continuation_package(stale)
    assert any("stale after a later integrated merge" in item for item in errors)


def test_post_merge_refresh_classifies_local_jira_mirror() -> None:
    payload = plan_post_merge_refresh(ROOT, apply=False)
    assert payload["user_action_required"] is False
    assert payload["jira_refresh"]["user_action_required"] is False
    assert payload["jira_refresh"]["local_mirror_present"] is True
