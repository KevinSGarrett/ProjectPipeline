from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

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
from project_pipeline.configuration.models import SecretReference


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


def test_credential_environment_keeps_process_bound_references_over_mutable_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "JIRA_API_TOKEN_REF=env://MUTABLE_FILE\nGITHUB_TOKEN_REF=env://MUTABLE_FILE\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JIRA_API_TOKEN_REF", "dpapi://C16B_JIRA_TOKEN")
    monkeypatch.setenv("GITHUB_TOKEN_REF", "gh-auth://default")

    environment = live_qualification_module._credential_environment(tmp_path)

    assert environment["JIRA_API_TOKEN_REF"] == "dpapi://C16B_JIRA_TOKEN"
    assert environment["GITHUB_TOKEN_REF"] == "gh-auth://default"


def test_campaign_credential_environment_never_loads_a_mutable_checkout_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "JIRA_API_TOKEN=must-not-be-loaded\nJIRA_API_TOKEN_REF=env://MUTABLE\n",
        encoding="utf-8",
    )
    campaign_environment = {
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "worker@example.test",
        "JIRA_API_TOKEN_REF": "dpapi://C16B_JIRA_TOKEN",
        "GITHUB_TOKEN_REF": "dpapi://C16B_GITHUB_TOKEN",
        "CAMPAIGN_PROJECT_ID": "PROJECT-PIPELINE",
        "CAMPAIGN_CYCLE_ID": "CYCLE-16-B",
        "CAMPAIGN_MACHINE_ID": "COMFY-V4-CPU-01",
        "CAMPAIGN_PRINCIPAL_SID": "S-1-5-21-1000",
        "CAMPAIGN_ID": "QCAMP-C16B-TEST",
        "CAMPAIGN_CANDIDATE_SHA": "a" * 40,
        "CAMPAIGN_CANDIDATE_TREE": "b" * 40,
        "CAMPAIGN_SCHEDULER_LEASE_ID": "CLEASE-C16B-TEST",
        "CAMPAIGN_FENCE_TOKEN": "CFENCE-C16B-TEST",
        "CAMPAIGN_CREDENTIAL_ENVELOPE_EXPIRES_AT_UTC": "2099-01-01T00:00:00+00:00",
        "CAMPAIGN_DEADLINE_AT_UTC": "2098-12-31T00:00:00+00:00",
    }
    for key, value in campaign_environment.items():
        monkeypatch.setenv(key, value)

    environment = live_qualification_module._credential_environment(tmp_path)

    assert environment["JIRA_API_TOKEN_REF"] == "dpapi://C16B_JIRA_TOKEN"
    assert "JIRA_API_TOKEN" not in environment


def test_campaign_github_resolution_rejects_ambient_cli_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    environment = {
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "worker@example.test",
        "JIRA_API_TOKEN_REF": "dpapi://C16B_JIRA_TOKEN",
        "GITHUB_TOKEN_REF": "gh-auth://default",
        "CAMPAIGN_PROJECT_ID": "PROJECT-PIPELINE",
        "CAMPAIGN_CYCLE_ID": "CYCLE-16-B",
        "CAMPAIGN_MACHINE_ID": "COMFY-V4-CPU-01",
        "CAMPAIGN_PRINCIPAL_SID": "S-1-5-21-1000",
        "CAMPAIGN_ID": "QCAMP-C16B-TEST",
        "CAMPAIGN_CANDIDATE_SHA": "a" * 40,
        "CAMPAIGN_CANDIDATE_TREE": "b" * 40,
        "CAMPAIGN_SCHEDULER_LEASE_ID": "CLEASE-C16B-TEST",
        "CAMPAIGN_FENCE_TOKEN": "CFENCE-C16B-TEST",
        "CAMPAIGN_CREDENTIAL_ENVELOPE_EXPIRES_AT_UTC": "2099-01-01T00:00:00+00:00",
        "CAMPAIGN_DEADLINE_AT_UTC": "2098-12-31T00:00:00+00:00",
    }
    monkeypatch.setattr(
        live_qualification_module, "_credential_environment", lambda _root: environment
    )

    def unexpected_cli_lookup(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("campaign resolution must not fall back to ambient gh auth")

    monkeypatch.setattr(live_qualification_module.subprocess, "run", unexpected_cli_lookup)

    assert live_qualification_module._resolve_github_token(root) == (None, "none")


def test_noncampaign_github_resolution_uses_ambient_cli_without_configured_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    calls: list[list[str]] = []
    monkeypatch.setattr(live_qualification_module, "_credential_environment", lambda _root: {})

    def cli_lookup(args: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="ambient-token\n")

    monkeypatch.setattr(live_qualification_module.subprocess, "run", cli_lookup)

    assert live_qualification_module._resolve_github_token(root) == ("ambient-token", "gh-auth")
    assert calls == [["gh", "auth", "token"]]


def test_noncampaign_github_resolution_keeps_gh_precedence_over_config_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    environment = {"GITHUB_TOKEN_REF": "env://CONFIGURED_TOKEN", "CONFIGURED_TOKEN": "config"}
    monkeypatch.setattr(
        live_qualification_module, "_credential_environment", lambda _root: environment
    )
    monkeypatch.setattr(
        live_qualification_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ambient-token\n"),
    )

    def unexpected_config_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("normal gh auth must take precedence over configured token resolution")

    monkeypatch.setattr(
        "project_pipeline.configuration.loader.load_runtime_configuration", unexpected_config_load
    )

    assert live_qualification_module._resolve_github_token(root) == ("ambient-token", "gh-auth")


@pytest.mark.parametrize(
    "cli_error",
    (
        OSError("gh unavailable"),
        subprocess.TimeoutExpired(("gh", "auth", "token"), 15),
    ),
)
def test_noncampaign_github_resolution_falls_back_to_config_when_cli_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    cli_error: BaseException,
) -> None:
    root = Path(__file__).resolve().parents[1]
    environment = {"GITHUB_TOKEN_REF": "env://CONFIGURED_TOKEN"}
    monkeypatch.setattr(
        live_qualification_module, "_credential_environment", lambda _root: environment
    )

    def unavailable_cli(*_args: object, **_kwargs: object) -> object:
        raise cli_error

    class ConfiguredSecretResolver:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.repository_root = _args[0]

        def resolve(self, _reference: SecretReference) -> str:
            return "configured-token"

    configuration = SimpleNamespace(
        settings=SimpleNamespace(
            integrations=SimpleNamespace(
                github_token=SecretReference(reference="env://CONFIGURED_TOKEN")
            )
        )
    )
    monkeypatch.setattr(live_qualification_module.subprocess, "run", unavailable_cli)
    monkeypatch.setattr(
        "project_pipeline.configuration.loader.load_runtime_configuration",
        lambda *_args, **_kwargs: configuration,
    )
    monkeypatch.setattr(
        "project_pipeline.configuration.secrets.SecretResolver", ConfiguredSecretResolver
    )

    assert live_qualification_module._resolve_github_token(root) == ("configured-token", "config")


def test_unrelated_campaign_prefixed_environment_key_does_not_force_campaign_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    environment = {"CAMPAIGN_DIAGNOSTIC_MARKER": "unrelated"}
    monkeypatch.setattr(
        live_qualification_module, "_credential_environment", lambda _root: environment
    )
    monkeypatch.setattr(
        live_qualification_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ambient-token\n"),
    )

    assert live_qualification_module._resolve_github_token(root) == ("ambient-token", "gh-auth")


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
    receipt: dict[str, object] = {
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
    receipt["receipt_sha256"] = live_qualification_module._coordinator_jira_receipt_digest(receipt)
    return receipt


def test_coordinator_jira_receipt_requires_fresh_exact_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "a" * 40
    tree = "b" * 40
    receipt = tmp_path / "coordinator-jira.json"
    signature = tmp_path / "coordinator-jira.sig"
    receipt.write_text(json.dumps(_coordinator_jira_receipt(sha=sha, tree=tree)), encoding="utf-8")
    signature.write_bytes(b"test signature")
    monkeypatch.setattr(
        live_qualification_module, "_verify_coordinator_jira_signature", lambda **_kwargs: True
    )

    accepted = _coordinator_jira_receipt_probe(
        receipt,
        signature,
        repository_root=tmp_path,
        expected_head=sha,
        expected_tree=tree,
    )
    assert accepted["valid"] is True
    assert accepted["write_readback_ok"] is True

    rejected = _coordinator_jira_receipt_probe(
        receipt,
        signature,
        repository_root=tmp_path,
        expected_head="c" * 40,
        expected_tree=tree,
    )
    assert rejected["valid"] is False
    assert rejected["reason"] == "coordinator_jira_receipt_policy_mismatch"


def test_coordinator_jira_receipt_rejects_content_address_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "a" * 40
    tree = "b" * 40
    payload = _coordinator_jira_receipt(sha=sha, tree=tree)
    payload["status"] = "FAILED"
    receipt = tmp_path / "coordinator-jira.json"
    signature = tmp_path / "coordinator-jira.sig"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    signature.write_bytes(b"test signature")
    monkeypatch.setattr(
        live_qualification_module, "_verify_coordinator_jira_signature", lambda **_kwargs: True
    )

    rejected = _coordinator_jira_receipt_probe(
        receipt,
        signature,
        repository_root=tmp_path,
        expected_head=sha,
        expected_tree=tree,
    )
    assert rejected["valid"] is False
    assert rejected["reason"] == "coordinator_jira_receipt_digest_mismatch"


def test_coordinator_jira_receipt_satisfies_cpu_governance_without_a_jira_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "a" * 40
    tree = "b" * 40
    receipt = tmp_path / "coordinator-jira.json"
    signature = tmp_path / "coordinator-jira.sig"
    receipt.write_text(json.dumps(_coordinator_jira_receipt(sha=sha, tree=tree)), encoding="utf-8")
    signature.write_bytes(b"test signature")
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
        lambda _root: pytest.fail("CPU must not read Jira after verifying coordinator proof"),
    )
    monkeypatch.setattr(
        live_qualification_module,
        "_probe_jira_write_readback",
        lambda _root: pytest.fail("CPU must not write Jira after verifying coordinator proof"),
    )
    monkeypatch.setattr(
        live_qualification_module, "_verify_coordinator_jira_signature", lambda **_kwargs: True
    )

    stage = _qualify_github_jira_governance(
        repo,
        candidate_head=sha,
        candidate_tree=tree,
        coordinator_jira_receipt=receipt,
        coordinator_jira_signature=signature,
    )
    assert stage.outcome is StageOutcome.PASSED
    assert stage.observations["jira_write_probe"]["execution_owner"] == "coordinator-receipt"
    assert stage.observations["local_jira_probe"]["not_attempted"] is True


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
    assert len(str(receipt["receipt_sha256"])) == 64
    assert receipt["secret_value_observed"] is False


def test_live_qualification_rejects_candidate_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    identities = [("a" * 40, "b" * 40), ("c" * 40, "d" * 40)]
    monkeypatch.setattr(live_qualification_module, "_git_identity", lambda _root: identities.pop(0))
    monkeypatch.setattr(live_qualification_module, "_git_checkout_clean", lambda _root: True)

    report = run_live_qualification(repository_root=repo, disposable_root=tmp_path / "runtime")
    by_id = {stage["stage_id"]: stage for stage in report["stages"]}
    integrity = by_id["candidate_checkout_integrity"]
    assert integrity["outcome"] == StageOutcome.FAILED.value
    assert integrity["observations"]["final_head"] == "c" * 40
