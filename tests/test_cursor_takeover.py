import json
import subprocess
import sys
from pathlib import Path

from project_pipeline.cursor_takeover import (
    CURSOR_GOAL,
    CandidateClassification,
    audit_issue_for_objective_progress,
    initialize_supervisor_state,
    record_supervisor_cycle,
    takeover_prompt,
    validate_cursor_takeover,
)


def test_cursor_control_package_uses_live_qualification_without_human_gate():
    root = Path(__file__).parents[1]
    report = validate_cursor_takeover(root)
    assert report.configuration_ready is True, report.errors
    assert report.unattended_ready is False
    forbidden = ("operator", "human", "ask the user", "approve this pr")
    assert not any(
        token in blocker.lower()
        for blocker in (*report.activation_blockers, *report.errors)
        for token in forbidden
    )
    if report.cursor_cli_path:
        assert report.activation_ready is True, report.activation_blockers
    else:
        assert report.activation_ready is False
        assert any(
            "Cursor Agent CLI is unavailable after native and WSL discovery" in blocker
            for blocker in report.activation_blockers
        )


def test_issue_audit_selects_missing_issue_specific_implementation(tmp_path: Path):
    issue = {
        "local_id": "PP-TASK-000379",
        "expected_implementation_artifacts": ["src/missing.py", "tests/test_missing.py"],
        "acceptance_criteria": [{"criterion_id": "AC-1", "verification": {"status": "PLANNED"}}],
        "completion_evidence": [],
    }
    audit = audit_issue_for_objective_progress(tmp_path, issue)
    assert audit.classification is CandidateClassification.IMPLEMENTATION_REQUIRED
    assert audit.missing_artifacts == ("src/missing.py", "tests/test_missing.py")


def test_issue_audit_routes_already_verified_work_to_bulk_reconciliation(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/ready.py").write_text("ready = True\n", encoding="utf-8")
    (tmp_path / "tests/test_ready.py").write_text("def test_ready(): pass\n", encoding="utf-8")
    issue = {
        "local_id": "PP-TASK-000379",
        "expected_implementation_artifacts": ["src/ready.py", "tests/test_ready.py"],
        "acceptance_criteria": [{"criterion_id": "AC-1", "verification": {"status": "VERIFIED"}}],
        "completion_evidence": ["EVID-TEST"],
    }
    audit = audit_issue_for_objective_progress(tmp_path, issue)
    assert audit.classification is CandidateClassification.RECONCILIATION_REQUIRED


def test_takeover_prompt_preserves_goal_and_prohibits_lifecycle_prs():
    prompt = takeover_prompt()
    assert CURSOR_GOAL in prompt
    assert "Never create a PR for a lifecycle transition" in prompt
    assert "at most two conflict-safe implementation lanes" in prompt


def test_cursor_shell_hook_denies_direct_external_mutation():
    root = Path(__file__).parents[1]
    hook = root / ".cursor/hooks/guard_shell.py"
    for command in ("git push origin main", 'powershell -Command "git push origin main"'):
        result = subprocess.run(
            [sys.executable, str(hook)],
            cwd=root,
            input=json.dumps({"hook_event_name": "beforeShellExecution", "command": command}),
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )
        response = json.loads(result.stdout)
        assert response["permission"] == "deny"
        assert "governed adapters" in response["agentMessage"]

    safe_result = subprocess.run(
        [sys.executable, str(hook)],
        cwd=root,
        input=json.dumps(
            {"hook_event_name": "beforeShellExecution", "command": "git status --short"}
        ),
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    assert json.loads(safe_result.stdout)["permission"] == "allow"


def test_missing_cursor_cli_is_external_precondition_not_human_gate(monkeypatch) -> None:
    from project_pipeline import cursor_takeover as takeover
    from project_pipeline.autonomy_runtime import cursor_cli_qualification

    monkeypatch.setattr(cursor_cli_qualification, "locate_cursor_cli_launch", lambda: None)
    root = Path(__file__).parents[1]
    report = takeover.validate_cursor_takeover(root)
    assert report.configuration_ready is True, report.errors
    assert report.activation_ready is False
    assert report.cursor_cli_path is None
    assert (
        "Cursor Agent CLI is unavailable after native and WSL discovery"
        in report.activation_blockers
    )
    assert not any(
        "human" in blocker.lower() or "operator" in blocker.lower()
        for blocker in report.activation_blockers
    )


def test_cursor_stop_hook_does_not_invent_continuation_without_durable_state(tmp_path: Path):
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / ".cursor/hooks/continue-cycle.py")],
        cwd=tmp_path,
        input='{"hook_event_name":"stop","status":"completed"}',
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    assert json.loads(result.stdout) == {}


def test_supervisor_stops_after_two_progressless_cycles(tmp_path: Path):
    initialize_supervisor_state(tmp_path)
    first = record_supervisor_cycle(
        tmp_path, objective_progress_units=0, completion_gate="NOT_COMPLETE"
    )
    second = record_supervisor_cycle(
        tmp_path, objective_progress_units=0, completion_gate="NOT_COMPLETE"
    )
    assert first.status == "READY"
    assert second.status == "PLANNER_DIAGNOSIS_REQUIRED"
    assert second.consecutive_progressless_cycles == 2
