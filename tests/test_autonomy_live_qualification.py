from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime import live_qualification as live_qualification_module
from project_pipeline.autonomy_runtime.live_qualification import (
    StageOutcome,
    _branch_absent_after_delete_readback,
    _coordinator_jira_receipt_probe,
    _qualify_github_jira_governance,
    create_coordinator_jira_governance_receipt,
    run_live_qualification,
    write_live_qualification_evidence,
)


def _scaffold_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "src" / "project_pipeline" / "github_steward").mkdir(parents=True)
    (repo / "src" / "project_pipeline" / "jira_steward").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    launcher = Path(__file__).resolve().parents[1] / "scripts" / "run_autonomy_runtime_service.py"
    (repo / "scripts" / "run_autonomy_runtime_service.py").write_text(
        launcher.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_live_qualification_passes_local_stages_and_blocks_cursor_cli(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    report = run_live_qualification(repository_root=repo, disposable_root=tmp_path / "runtime")
    by_id = {stage["stage_id"]: stage for stage in report["stages"]}
    windows = by_id["windows_service_foreground"]
    assert windows["outcome"] == StageOutcome.PASSED.value
    assert windows["observations"]["plan_valid"] is True
    assert windows["observations"]["checkpoint_status"] == "STOPPED"
    assert windows["observations"]["stale_pid_detected"] is True

    command_center = by_id["command_center_truth"]
    assert command_center["outcome"] == StageOutcome.PASSED.value
    assert command_center["observations"]["context_summary"]["source"] == "durable_state"
    assert (
        command_center["observations"]["context_summary"]["windows_service"]["checkpoint_exists"]
        is True
    )

    assert by_id["local_provider_dispatch"]["outcome"] == StageOutcome.PASSED.value

    governance = by_id["github_jira_governance"]
    assert governance["outcome"] == StageOutcome.BLOCKED_EXTERNAL.value
    assert governance["observations"]["adapters_present"] is True
    assert "github_probe" in governance["observations"]
    assert "jira_probe" in governance["observations"]
    assert "github_write_probe" in governance["observations"]
    assert "jira_write_probe" in governance["observations"]
    assert governance["observations"]["write_readback_ok"] is False

    cursor_cli = by_id["cursor_cli_provider_dispatch"]
    assert cursor_cli["outcome"] == StageOutcome.FAILED.value
    encoded = json.dumps(report)
    assert "HUMAN_REQUIRED" not in encoded
    assert "operator session" not in encoded
    assert "await human" not in encoded
    assert cursor_cli["observations"]["outcome"] == StageOutcome.FAILED.value


def test_write_live_qualification_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    output = write_live_qualification_evidence(
        repository_root=repo, disposable_root=tmp_path / "runtime"
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["task_id"] == "PP-TASK-000384"
    assert output.name == "live_qualification_latest.json"
    assert payload["report_sha256"]
    assert "bound_head" in payload
    assert "bound_tree" in payload


def test_live_qualification_rerun_clears_same_disposable_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    runtime = tmp_path / "runtime"
    first = run_live_qualification(repository_root=repo, disposable_root=runtime)
    assert first["stages"][1]["outcome"] == StageOutcome.PASSED.value
    second = run_live_qualification(repository_root=repo, disposable_root=runtime)
    assert second["stages"][1]["stage_id"] == "command_center_truth"
    assert second["stages"][1]["outcome"] == StageOutcome.PASSED.value


def test_live_qualification_fails_closed_when_runtime_root_stays_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(
        live_qualification_module,
        "remove_disposable_workspace",
        lambda _path, **_kwargs: False,
    )
    with pytest.raises(RuntimeError, match="still locked"):
        run_live_qualification(repository_root=repo, disposable_root=runtime)


def test_github_branch_delete_readback_tolerates_a_stale_first_listing() -> None:
    class Branch:
        name = "qual/pp384-live-probe"

    class Adapter:
        def __init__(self) -> None:
            self.calls = 0

        def iter_branches(self, _repository_slug: str):
            self.calls += 1
            return (Branch(),) if self.calls == 1 else ()

    delays: list[float] = []
    assert _branch_absent_after_delete_readback(
        Adapter(),
        repository_slug="owner/repo",
        branch_name="qual/pp384-live-probe",
        attempts=2,
        delay_seconds=0.01,
        sleeper=delays.append,
    )
    assert delays == [0.01]


def _coordinator_jira_receipt(*, sha: str, tree: str) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "kind": "pp384_coordinator_jira_governance",
        "status": "PASSED",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "task_id": "PP-TASK-000384",
        "coordinator_id": "PRIMARY-CODEX-WORKSTATION",
        "candidate": {"sha": sha, "tree": tree},
        "jira_probe": {"read_ok": True},
        "jira_write_probe": {
            "write_readback_ok": True,
            "remote_key": "PP-384",
            "provider_id": "jira-cloud",
        },
        "secret_value_observed": False,
    }


def test_coordinator_jira_receipt_requires_fresh_exact_candidate(tmp_path: Path) -> None:
    sha = "a" * 40
    tree = "b" * 40
    receipt = tmp_path / "coordinator-jira.json"
    receipt.write_text(json.dumps(_coordinator_jira_receipt(sha=sha, tree=tree)), encoding="utf-8")

    accepted = _coordinator_jira_receipt_probe(receipt, expected_head=sha, expected_tree=tree)
    assert accepted["valid"] is True
    assert accepted["write_readback_ok"] is True

    rejected = _coordinator_jira_receipt_probe(receipt, expected_head="c" * 40, expected_tree=tree)
    assert rejected["valid"] is False
    assert rejected["reason"] == "coordinator_jira_receipt_policy_mismatch"


def test_coordinator_jira_receipt_satisfies_cpu_governance_without_a_jira_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "a" * 40
    tree = "b" * 40
    receipt = tmp_path / "coordinator-jira.json"
    receipt.write_text(json.dumps(_coordinator_jira_receipt(sha=sha, tree=tree)), encoding="utf-8")
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    monkeypatch.setattr(
        live_qualification_module, "_probe_github_read", lambda _slug: {"read_ok": True}
    )
    monkeypatch.setattr(
        live_qualification_module,
        "_resolve_github_token",
        lambda _root: ("scoped-token", "test"),
    )
    monkeypatch.setattr(
        live_qualification_module,
        "_probe_github_write_readback",
        lambda _slug, _token: {"write_readback_ok": True},
    )
    monkeypatch.setattr(
        live_qualification_module,
        "_probe_jira_read",
        lambda _root: {"credential_available": False},
    )
    monkeypatch.setattr(
        live_qualification_module,
        "_probe_jira_write_readback",
        lambda _root: {"write_readback_ok": False},
    )

    stage = _qualify_github_jira_governance(
        repo,
        candidate_head=sha,
        candidate_tree=tree,
        coordinator_jira_receipt=receipt,
    )
    assert stage.outcome is StageOutcome.PASSED
    assert stage.observations["jira_write_probe"]["execution_owner"] == "coordinator-receipt"


def test_coordinator_probe_receipt_contains_no_jira_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        live_qualification_module, "_git_identity", lambda _root: ("a" * 40, "b" * 40)
    )
    monkeypatch.setattr(
        live_qualification_module, "_probe_jira_read", lambda _root: {"read_ok": True}
    )
    monkeypatch.setattr(
        live_qualification_module,
        "_probe_jira_write_readback",
        lambda _root: {"write_readback_ok": True, "remote_key": "PP-384"},
    )
    receipt = create_coordinator_jira_governance_receipt(repository_root=Path("."))
    assert receipt["status"] == "PASSED"
    assert receipt["secret_value_observed"] is False
