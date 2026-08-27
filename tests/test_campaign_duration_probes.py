from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime import cursor_cli_qualification as cursor_cli_module
from project_pipeline.autonomy_runtime import duration_probes as duration_probe_module
from project_pipeline.autonomy_runtime.command_execution import (
    command_is_allowlisted,
    command_kind,
    evaluate_command_semantics,
)
from project_pipeline.autonomy_runtime.duration_probes import (
    _probe_cursor,
    _probe_director_restart,
    _probe_jira,
    required_probe_ids,
    run_duration_probe,
)
from project_pipeline.command_center import autonomy_director as autonomy_director_module

ROOT = Path(__file__).resolve().parents[1]


def test_duration_probe_surface_is_broader_than_local_validation() -> None:
    required = required_probe_ids()
    assert {
        "command_center_projection",
        "autonomy_director_restart",
        "desktop_artifact_health",
        "cursor_cli_provider_dispatch",
        "github_live_readback",
        "jira_live_readback",
        "campaign_persistence_integrity",
        "recovery_isolation",
    } <= required
    assert len(required) > 5


def test_duration_probe_is_allowlisted_and_requires_subject_evidence() -> None:
    command = [sys.executable, str(ROOT / "scripts" / "campaign_duration_probe.py")]
    assert command_is_allowlisted(command, repository_root=ROOT) is True
    assert command_kind(command) == "duration-probe"
    missing_subject = evaluate_command_semantics(
        command,
        exit_code=0,
        stdout=json.dumps({"ok": True, "probe_id": "candidate_identity"}),
        expected_sha="a" * 40,
        expected_tree="b" * 40,
    )
    assert missing_subject["result"] == "FAILED"
    verified = evaluate_command_semantics(
        command,
        exit_code=0,
        stdout=json.dumps(
            {
                "ok": True,
                "probe_id": "candidate_identity",
                "subject": {
                    "sha": "a" * 40,
                    "tree": "b" * 40,
                    "clean": True,
                    "inspect_ok": True,
                },
                "evidence_sha256": "c" * 64,
            }
        ),
        expected_sha="a" * 40,
        expected_tree="b" * 40,
    )
    assert verified["result"] == "PASSED"


def test_repository_validation_pass_summary_is_machine_classified() -> None:
    command = [sys.executable, "-m", "project_pipeline", "validate", "--root", str(ROOT)]
    passed = evaluate_command_semantics(
        command,
        exit_code=0,
        stdout="Repository validation: PASS\nChecks: 44 | Errors: 0 | Warnings: 0\n",
    )
    assert passed["result"] == "PASSED"
    assert passed["reason"] == "repository-validation-pass"
    assert passed["parsed"] == {"checks": 44, "errors": [], "warnings": 0}

    passed_with_notice = evaluate_command_semantics(
        command,
        exit_code=0,
        stdout=(
            "Repository validation: PASS\n"
            "Checks: 44 | Errors: 0 | Warnings: 0\n"
            "INFO PUBLIC001 [README.md]: Validated a standalone public source checkout; "
            "local delivery records are optional.\n"
        ),
    )
    assert passed_with_notice["result"] == "PASSED"
    assert passed_with_notice["reason"] == "repository-validation-pass"

    rejected = evaluate_command_semantics(
        command,
        exit_code=0,
        stdout="Repository validation: PASS\nChecks: 44 | Errors: 1 | Warnings: 0\n",
    )
    assert rejected["result"] == "FAILED"
    assert rejected["reason"] == "repository-validation-summary-invalid"


def test_cursor_duration_probe_keeps_workspace_disposable_but_uses_durable_resolver(
    monkeypatch, tmp_path: Path
) -> None:
    observed: dict[str, object] = {}

    def qualify_cursor_cli_provider(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {
            "outcome": "PASSED",
            "provider_id": "provider:cursor-cli",
            "live_dispatch": {"ok": True},
            "replay_verified": True,
            "reasons": [],
        }

    monkeypatch.setattr(
        cursor_cli_module,
        "qualify_cursor_cli_provider",
        qualify_cursor_cli_provider,
    )
    root = tmp_path / "candidate"
    state_root = tmp_path / "campaign-state"

    report = _probe_cursor(root, state_root)

    assert report["outcome"] == "PASSED"
    assert observed["repository_root"] == root
    assert observed["disposable_root"] == state_root / "cursor-disposable"
    assert "durable_dir" not in observed


def test_duration_probe_rejects_state_nested_in_candidate(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    with pytest.raises(ValueError, match="state_root must be outside"):
        run_duration_probe(
            "candidate_identity",
            repository_root=candidate,
            expected_sha="a" * 40,
            expected_tree="b" * 40,
            state_root=candidate / ".local" / "duration-probes",
        )

    assert not (candidate / ".local").exists()


def test_duration_probe_default_state_root_is_external_to_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    observed: dict[str, Path] = {}
    subject = {"sha": "a" * 40, "tree": "b" * 40, "clean": True, "inspect_ok": True}

    monkeypatch.setattr(duration_probe_module, "_subject", lambda _root: subject)
    monkeypatch.setattr(
        duration_probe_module, "_candidate_evidence", lambda *_args, **_kwargs: (True, {})
    )

    def director_probe(_root: Path, state_root: Path) -> dict[str, object]:
        observed["state_root"] = state_root
        return {
            "recovered": True,
            "persisted_decision_count": 1,
        }

    monkeypatch.setattr(duration_probe_module, "_probe_director_restart", director_probe)

    result = run_duration_probe(
        "autonomy_director_restart",
        repository_root=candidate,
        expected_sha="a" * 40,
        expected_tree="b" * 40,
    )

    assert result["ok"] is True
    assert not observed["state_root"].is_relative_to(candidate)
    assert not (candidate / ".local").exists()


def test_director_restart_probe_is_not_applicable_without_private_traceability(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def raise_missing_requirements(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("plans/_traceability/requirements.jsonl")

    monkeypatch.setattr(
        autonomy_director_module, "evaluate_live_control", raise_missing_requirements
    )
    result = _probe_director_restart(tmp_path / "candidate", tmp_path / "state")
    assert result["state"] == "NOT_APPLICABLE_PUBLIC_SOURCE"
    assert result["recovered"] is True
    assert result["persisted_decision_count"] == 1


def test_director_restart_not_applicable_state_is_accepted_when_identity_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    subject = {"sha": "a" * 40, "tree": "b" * 40, "clean": True, "inspect_ok": True}

    monkeypatch.setattr(duration_probe_module, "_subject", lambda _root: subject)
    monkeypatch.setattr(
        duration_probe_module, "_candidate_evidence", lambda *_args, **_kwargs: (True, {})
    )
    monkeypatch.setattr(
        duration_probe_module,
        "_probe_director_restart",
        lambda *_args, **_kwargs: {"state": "NOT_APPLICABLE_PUBLIC_SOURCE"},
    )

    result = run_duration_probe(
        "autonomy_director_restart",
        repository_root=candidate,
        expected_sha="a" * 40,
        expected_tree="b" * 40,
    )

    assert result["ok"] is True
    assert result["observations"]["state"] == "NOT_APPLICABLE_PUBLIC_SOURCE"


def test_jira_duration_probe_uses_remote_issue_status_name(monkeypatch) -> None:
    class RemoteJiraIssue:
        status_name = "In Progress"

    class JiraAdapter:
        discarded = False

        def get_issue(self, key: str) -> RemoteJiraIssue:
            assert key in {"PP-384", "PP-385", "PP-391", "PP-393"}
            return RemoteJiraIssue()

        def discard_secret_material(self) -> None:
            self.discarded = True

    adapter = JiraAdapter()

    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.live_qualification._build_jira_adapter",
        lambda _root: adapter,
    )

    result = _probe_jira(ROOT)

    assert result == {
        "ok": True,
        "issues": {
            "PP-384": "In Progress",
            "PP-385": "In Progress",
            "PP-391": "In Progress",
            "PP-393": "In Progress",
        },
    }
    assert adapter.discarded is True
