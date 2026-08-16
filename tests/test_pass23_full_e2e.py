import json

from project_pipeline.control import RecommendationDisposition, evaluate_recommendation_authority
from project_pipeline.verification.e2e import run_full_e2e, write_full_e2e_report


def test_recommendation_conflicting_with_canonical_plan_escalates():
    decision = evaluate_recommendation_authority("rec:plan", conflicts_with_canonical_plan=True)
    assert decision.disposition is RecommendationDisposition.ESCALATE
    assert decision.may_apply is False


def test_recommendation_conflicting_with_policy_is_rejected():
    decision = evaluate_recommendation_authority("rec:policy", conflicts_with_policy=True)
    assert decision.disposition is RecommendationDisposition.REJECT
    assert decision.may_apply is False


def test_aligned_recommendation_is_advisory_eligible():
    decision = evaluate_recommendation_authority("rec:ok")
    assert decision.disposition is RecommendationDisposition.ACCEPT
    assert decision.may_apply is True
    assert decision.canonical_authority == "PROJECT_PIPELINE"


def test_pass23_full_e2e_journeys_cover_required_chain(project_root):
    report = run_full_e2e(project_root)
    assert report["overall_passed"] is True
    assert report["live_external_mutation_performed"] is False
    first = report["journeys"][0]
    names = {item["name"] for item in first["stages"]}
    required = {
        "project_intake",
        "requirement_compilation",
        "jira_generation_and_reconciliation",
        "sequencing_and_human_gate",
        "dynamic_scheduling",
        "delegation_and_context_compilation",
        "agent_execution_provider_outage",
        "canonical_authority_conflict",
        "independent_review_separation",
        "git_pr_merge_gate",
        "durable_restart_and_unknown_outcome",
        "incident_human_repair_reconciliation",
        "independent_completion_gate",
        "command_center_visibility",
    }
    assert required.issubset(names)
    assert all(journey["passed"] for journey in report["journeys"])


def test_external_legs_are_explicitly_blocked_not_falsely_verified(project_root):
    report = run_full_e2e(project_root)
    stages = report["journeys"][0]["stages"]
    blocked = [item for item in stages if item["execution_mode"] == "BLOCKED_EXTERNAL"]
    assert len(blocked) == 8
    assert all(item["state"] == "EXPECTED_BLOCK" for item in blocked)


def test_pass23_report_is_persisted_with_digest(project_root, tmp_path):
    path = write_full_e2e_report(project_root, tmp_path / "report.json")
    report = json.loads(path.read_text())
    assert report["overall_passed"] is True
    assert len(report["report_sha256"]) == 64
