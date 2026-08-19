from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from project_pipeline.assurance import build_repository_gate_facts, evaluate_completion_gate
from project_pipeline.convergence import build_convergence_audit, validate_final_convergence
from project_pipeline.domain.security import SecurityAuditEvent, security_identifier
from project_pipeline.persistence.migrations import SQLiteMigrationRunner
from project_pipeline.release_hardening.post_deploy import (
    PostDeploymentObservation,
    verify_post_deployment,
)
from project_pipeline.requirements import load_requirement_catalog
from project_pipeline.resilience import RunbookActionResult, RunbookExecutor, load_approved_runbook
from project_pipeline.security.persistence import SecurityStore

ROOT = Path(__file__).resolve().parents[1]


def audit_event(name: str) -> SecurityAuditEvent:
    return SecurityAuditEvent(
        audit_id=security_identifier("SAUDIT", name),
        event_type="TEST",
        actor_identity_id="actor",
        target="target",
        correlation_id="corr",
        outcome="PASS",
        details={"name": name},
    )


def test_ppdb_0019_database_enforces_append_only_audit_history(tmp_path):
    db = tmp_path / "audit.db"
    first = audit_event("one")
    with SecurityStore(db, ROOT) as store:
        store.save_audit_event(first)
        with pytest.raises(sqlite3.IntegrityError):
            store.save_audit_event(first)
        with pytest.raises(sqlite3.IntegrityError):
            store.db.execute(
                "UPDATE security_audit_events SET event_type='MUTATED' WHERE audit_id=?",
                (first.audit_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.db.execute(
                "DELETE FROM security_audit_events WHERE audit_id=?", (first.audit_id,)
            )
        row = store.db.execute(
            "SELECT event_type FROM security_audit_events WHERE audit_id=?", (first.audit_id,)
        ).fetchone()
        assert row[0] == "TEST"


def test_ppdb_0020_is_latest_and_reversible_without_removing_ppdb_0019(tmp_path):
    db = sqlite3.connect(tmp_path / "m.db")
    runner = SQLiteMigrationRunner(db, ROOT)
    runner.apply_all()
    assert runner.status().latest_applied == "PPDB-0022"
    runner.rollback_last()
    ids = {r[0] for r in db.execute("SELECT migration_id FROM schema_migrations")}
    assert "PPDB-0021" in ids and "PPDB-0022" not in ids
    runner.rollback_last()
    ids = {r[0] for r in db.execute("SELECT migration_id FROM schema_migrations")}
    assert "PPDB-0020" in ids and "PPDB-0021" not in ids


def test_versioned_approved_runbook_dry_run_is_non_mutating_and_recorded():
    book = load_approved_runbook(ROOT / "config/runbooks/recovery_control_machine.json")
    records = []
    handlers = {
        name: (
            lambda step, ctx: RunbookActionResult(
                step_id=step.step_id,
                action=step.action,
                success=True,
                verified=True,
                observation="ok",
            )
        )
        for name in ("verify_witness", "reconcile_state", "resume_eligible_work")
    }
    result = RunbookExecutor(handlers, audit_sink=records.append).execute(book, apply=False)
    assert result.completed and result.mode == "DRY_RUN" and len(records) == 3
    assert all("runbook_fingerprint" in row for row in records)


def test_runbook_executor_rejects_unapproved_and_honors_stop_condition():
    book = load_approved_runbook(ROOT / "config/runbooks/recovery_control_machine.json")
    with pytest.raises(PermissionError):
        RunbookExecutor({}).execute(book.model_copy(update={"approved": False}), apply=True)
    seen = []

    def fail(step, ctx):
        seen.append(step.step_id)
        return RunbookActionResult(
            step_id=step.step_id,
            action=step.action,
            success=True,
            verified=False,
            observation="verification failed",
        )

    handlers = {"verify_witness": fail, "reconcile_state": fail, "resume_eligible_work": fail}
    result = RunbookExecutor(handlers).execute(book, apply=True)
    assert (
        not result.completed
        and result.stopped_at_step_id == "verify-witness"
        and seen == ["verify-witness"]
    )


def test_post_deployment_verifier_requires_every_check_and_live_target_evidence():
    names = (
        "health",
        "version",
        "migration",
        "integration",
        "security",
        "telemetry",
        "golden_journey",
    )
    missing = verify_post_deployment(
        PostDeploymentObservation(
            target_environment="staging",
            checks={name: True for name in names if name != "security"},
        )
    )
    assert missing.state == "FAIL" and "security" in missing.missing_or_failed_checks
    source_only = verify_post_deployment(
        PostDeploymentObservation(
            target_environment="staging", checks={name: True for name in names}, live_target=False
        )
    )
    assert source_only.state == "BLOCKED_EXTERNAL" and not source_only.live_target_verified
    live = verify_post_deployment(
        PostDeploymentObservation(
            target_environment="staging",
            checks={name: True for name in names},
            live_target=True,
            evidence_ids=("EVID-LIVE",),
        )
    )
    assert live.state == "PASS" and live.live_target_verified


def test_aws_budget_circuit_breaker_source_is_fail_closed_and_independent():
    main = (ROOT / "infrastructure/aws/terraform/main.tf").read_text()
    variables = (ROOT / "infrastructure/aws/terraform/variables.tf").read_text()
    assert 'resource "aws_budgets_budget_action" "monthly_guardrail"' in main
    assert 'action_type        = "APPLY_IAM_POLICY"' in main
    assert 'approval_model     = "AUTOMATIC"' in main
    assert "action_threshold_value = 100" in main
    assert "default = false" in variables and "enable_budget_circuit_breaker" in variables
    assert "precondition {" in main and "budget_guardrail_policy_arn" in main


def test_final_convergence_audit_enumerates_every_accepted_requirement_and_keeps_truth_boundary():
    report = build_convergence_audit(ROOT)
    expected_accepted = sum(
        1
        for requirement in load_requirement_catalog(ROOT)
        if requirement.get("disposition") == "ACCEPTED"
    )
    assert expected_accepted == 352
    assert report["accepted_requirement_count"] == expected_accepted
    assert len(report["requirements"]) == expected_accepted
    assert report["project_complete"] is False
    assert report["completion_gate_state"] == "NOT_COMPLETE"
    assert report["truth_boundary"].startswith("audit completion means")
    assert not report["orphan_non_epic_jira_ids"]
    assert report["audit_complete"] is True
    assert report["audit_dimensions"]["all_dimensions_covered"] is True
    expected = {
        "requirement_dispositions",
        "plan_areas",
        "work_relationships",
        "implementation_mappings",
        "tests",
        "evidence",
        "decisions",
        "dependencies",
        "security_controls",
        "journeys",
        "deployment_artifacts",
        "runbooks",
        "blockers",
        "source_links",
        "upstream_usage",
    }
    assert set(report["audit_dimensions"]["dimensions"]) == expected


def test_completion_gate_cannot_be_overridden_by_final_audit():
    gate = evaluate_completion_gate(build_repository_gate_facts(ROOT, "PROJECT-PIPELINE"))
    assert gate.state.value == "NOT_COMPLETE"
    assert any(not q.passed for q in gate.questions)


def test_final_convergence_validator_is_clean_after_report_generation():
    assert validate_final_convergence(ROOT) == []
