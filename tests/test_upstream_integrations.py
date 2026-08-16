from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from project_pipeline.contracts.envelopes import ActionIntent, ApprovalState
from project_pipeline.upstream_integrations import (
    CodexExecAdapter,
    CosignVerifyAdapter,
    GeminiCliAdapter,
    GitleaksAdapter,
    InspectAIAdapter,
    OsvScannerAdapter,
    PromptfooAdapter,
    RepomixAdapter,
    SwerexRuntimeAdapter,
    UpstreamIntegrationError,
    ZizmorAdapter,
    atlassian_mcp_profile,
    github_mcp_profile,
    require_mcp_write,
)


def completed(argv, *, stdout="", stderr="", code=0):
    return subprocess.CompletedProcess(list(argv), code, stdout=stdout, stderr=stderr)


def approved_intent(authority: str, target: str, operation: str) -> ActionIntent:
    return ActionIntent(
        actor_id="actor:test",
        authority=authority,
        target=target,
        operation=operation,
        idempotency_key="integration-test-key",
        approval_state=ApprovalState.APPROVED,
        correlation_id="corr:test",
    )


def test_codex_read_only_plan_uses_safe_noninteractive_contract(tmp_path: Path):
    plan = CodexExecAdapter().plan(tmp_path, "inspect this repository")
    assert plan.argv[:2] == ("codex", "exec")
    assert "--json" in plan.argv
    assert "--ephemeral" in plan.argv
    assert "--ignore-user-config" in plan.argv
    assert plan.argv[plan.argv.index("--sandbox") : plan.argv.index("--sandbox") + 2] == (
        "--sandbox",
        "read-only",
    )
    assert plan.argv[-1] == "-"
    assert plan.stdin == "inspect this repository"
    assert "--dangerously-bypass-approvals-and-sandbox" not in plan.argv
    assert not plan.mutating


def test_codex_mutation_requires_project_pipeline_approval(tmp_path: Path):
    calls = []

    def runner(argv, cwd, stdin, timeout, env):
        calls.append(tuple(argv))
        return completed(argv, stdout='{"type":"result"}\n')

    adapter = CodexExecAdapter(runner=runner)
    plan = adapter.plan(tmp_path, "make a bounded edit", mutating=True)
    assert "--approve-for-me" in plan.argv
    with pytest.raises(UpstreamIntegrationError):
        adapter.execute(plan, allow_network=True)
    outcome = adapter.execute(
        plan,
        allow_network=True,
        intent=approved_intent("execution.runtime", str(tmp_path.resolve()), "worker.execute"),
    )
    assert outcome.state == "SUCCEEDED"
    assert outcome.parsed == [{"type": "result"}]
    assert calls


def test_gemini_plan_never_uses_yolo_and_uses_stream_json(tmp_path: Path):
    plan = GeminiCliAdapter().plan(tmp_path, "review", mutating=False)
    assert "--output-format" in plan.argv and "stream-json" in plan.argv
    assert plan.argv[plan.argv.index("--approval-mode") + 1] == "plan"
    assert "yolo" not in plan.argv and "--yolo" not in plan.argv
    write_plan = GeminiCliAdapter().plan(tmp_path, "edit", mutating=True)
    assert write_plan.argv[write_plan.argv.index("--approval-mode") + 1] == "auto_edit"


def test_network_enabled_workers_fail_closed_without_allowance(tmp_path: Path):
    for plan, adapter in [
        (CodexExecAdapter().plan(tmp_path, "review"), CodexExecAdapter()),
        (GeminiCliAdapter().plan(tmp_path, "review"), GeminiCliAdapter()),
    ]:
        with pytest.raises(UpstreamIntegrationError):
            adapter.execute(plan)


def test_repomix_plan_keeps_security_checks_and_enforces_token_budget(tmp_path: Path):
    plan = RepomixAdapter().plan(
        tmp_path, token_budget=20_000, include=("src/**",), ignore=("tests/**",)
    )
    assert "--compress" in plan.argv
    assert "--output-show-line-numbers" in plan.argv
    assert plan.argv[plan.argv.index("--token-budget") + 1] == "20000"
    assert "--no-security-check" not in plan.argv
    assert "--remote-trust-config" not in plan.argv
    with pytest.raises(ValueError):
        RepomixAdapter().plan(tmp_path, token_budget=0)


def test_repomix_parses_machine_readable_output(tmp_path: Path):
    def runner(argv, cwd, stdin, timeout, env):
        return completed(argv, stdout=json.dumps({"files": [{"path": "src/a.py"}]}))

    adapter = RepomixAdapter(runner=runner)
    outcome = adapter.execute(adapter.plan(tmp_path, token_budget=1000))
    assert outcome.parsed == {"files": [{"path": "src/a.py"}]}


def test_official_mcp_profiles_are_read_only_by_default_and_secret_referenced():
    github = github_mcp_profile()
    atlassian = atlassian_mcp_profile()
    assert github.endpoint == "https://api.githubcopilot.com/mcp/"
    assert atlassian.endpoint == "https://mcp.atlassian.com/v1/mcp/authv2"
    assert github.secret_reference.startswith("env:")
    assert atlassian.secret_reference.startswith("env:")
    assert not github.writes_default_enabled and not atlassian.writes_default_enabled
    assert github.secret_reference == "env:GITHUB_MCP_TOKEN"
    assert (
        github.request_headers(secret_value="runtime-secret")["Authorization"]
        == "Bearer runtime-secret"
    )
    assert "runtime-secret" not in repr(github)


def test_mcp_write_requires_owning_steward_intent():
    profile = github_mcp_profile()
    with pytest.raises(UpstreamIntegrationError):
        require_mcp_write(profile, None, operation="mcp.write")
    wrong = approved_intent("jira.steward", profile.endpoint, "mcp.write")
    with pytest.raises(UpstreamIntegrationError):
        require_mcp_write(profile, wrong, operation="mcp.write")
    good = approved_intent("github.steward", profile.endpoint, "mcp.write")
    require_mcp_write(profile, good, operation="mcp.write")


def test_promptfoo_eval_is_local_artifact_bounded_and_no_share(tmp_path: Path):
    config = tmp_path / "promptfooconfig.yaml"
    config.write_text("prompts: []\nproviders: []\ntests: []\n", encoding="utf-8")
    plan = PromptfooAdapter().plan_eval(
        tmp_path, config, Path(".local/evals/result.json"), max_concurrency=2
    )
    assert plan.argv[:2] == ("promptfoo", "eval")
    assert "--no-share" in plan.argv
    assert "--max-concurrency" in plan.argv
    assert str(tmp_path.resolve()) in plan.cwd
    with pytest.raises(ValueError):
        PromptfooAdapter().plan_eval(tmp_path, config, Path("../escape.json"))


def test_promptfoo_network_execution_requires_allowance(tmp_path: Path):
    config = tmp_path / "promptfooconfig.yaml"
    config.write_text("prompts: []\n", encoding="utf-8")
    adapter = PromptfooAdapter(runner=lambda a, c, s, t, e: completed(a))
    plan = adapter.plan_eval(tmp_path, config, Path("result.json"))
    with pytest.raises(UpstreamIntegrationError):
        adapter.execute(plan)
    assert adapter.execute(plan, allow_network=True).state == "SUCCEEDED"


def test_inspect_ai_plan_is_constrained_and_network_gated(tmp_path: Path):
    adapter = InspectAIAdapter(runner=lambda a, c, s, t, e: completed(a))
    plan = adapter.plan_eval(
        tmp_path, "my_eval", model="mock/model", log_dir=Path(".local/inspect")
    )
    assert plan.argv[:2] == ("inspect", "eval")
    assert "--model" in plan.argv and "--log-dir" in plan.argv
    with pytest.raises(UpstreamIntegrationError):
        adapter.execute(plan)
    assert adapter.execute(plan, allow_network=True).returncode == 0
    with pytest.raises(ValueError):
        adapter.plan_eval(tmp_path, "--bad", model="mock/model", log_dir=Path("logs"))


def test_gitleaks_uses_current_git_subcommand_and_full_redaction(tmp_path: Path):
    plan = GitleaksAdapter().plan_git_scan(tmp_path, Path(".local/security/gitleaks.json"))
    assert plan.argv[1] == "git"
    assert "--redact=100" in plan.argv
    assert "detect" not in plan.argv and "protect" not in plan.argv
    assert plan.network_required is False


def test_osv_scanner_uses_read_only_source_scan_and_machine_output(tmp_path: Path):
    plan = OsvScannerAdapter().plan_source_scan(tmp_path, offline=True)
    assert plan.argv[:2] == ("osv-scanner", "--offline")
    assert "scan" in plan.argv and "source" in plan.argv
    assert plan.argv[plan.argv.index("--format") : plan.argv.index("--format") + 2] == (
        "--format",
        "json",
    )
    assert "fix" not in plan.argv
    assert not plan.network_required


def test_osv_online_scan_requires_explicit_network_allowance(tmp_path: Path):
    adapter = OsvScannerAdapter(runner=lambda a, c, s, t, e: completed(a, stdout='{"results":[]}'))
    plan = adapter.plan_source_scan(tmp_path, offline=False)
    with pytest.raises(UpstreamIntegrationError):
        adapter.execute(plan)
    outcome = adapter.execute(plan, allow_network=True)
    assert outcome.parsed == {"results": []}


def test_cosign_verification_requires_digest_and_never_signs(tmp_path: Path):
    adapter = CosignVerifyAdapter()
    with pytest.raises(ValueError):
        adapter.plan_verify(
            tmp_path, "example/image:latest", certificate_identity="x", certificate_oidc_issuer="y"
        )
    plan = adapter.plan_verify(
        tmp_path,
        "example/image@sha256:" + "a" * 64,
        certificate_identity="https://github.com/example/repo/.github/workflows/release.yml@refs/heads/main",
        certificate_oidc_issuer="https://token.actions.githubusercontent.com",
    )
    assert plan.argv[1] == "verify"
    assert "sign" not in plan.argv
    assert plan.network_required


def test_zizmor_is_offline_strict_and_versioned_json(tmp_path: Path):
    plan = ZizmorAdapter().plan_offline_audit(tmp_path)
    assert plan.argv[1:4] == ("--offline", "--strict-collection", "--format=json-v1")
    assert not plan.network_required
    assert "--fix" not in plan.argv


class FakeRuntime:
    async def execute(self, command):
        if isinstance(command, dict):
            assert command["shell"] is False
            argv = command["command"]
        else:
            assert command.shell is False
            argv = command.command
        return SimpleNamespace(stdout="ok:" + argv[0], stderr="", exit_code=0)


class FakeDeployment:
    command_factory = staticmethod(lambda **kwargs: kwargs)

    def __init__(self):
        self.runtime = FakeRuntime()
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


def test_swerex_adapter_uses_runtime_without_shell_and_lifecycle(tmp_path: Path):
    created = []

    def factory():
        d = FakeDeployment()
        created.append(d)
        return d

    adapter = SwerexRuntimeAdapter(deployment_factory=factory)
    plan = adapter.plan(tmp_path, ("python", "-V"))
    result = asyncio.run(adapter.execute(plan))
    assert result["stdout"] == "ok:python"
    assert result["upstream_id"] == "UPSTREAM-102"
    assert created[0].started and created[0].stopped


def test_swerex_mutating_execution_requires_approval(tmp_path: Path):
    adapter = SwerexRuntimeAdapter(deployment_factory=FakeDeployment)
    plan = adapter.plan(tmp_path, ("python", "script.py"), mutating=True)
    with pytest.raises(UpstreamIntegrationError):
        asyncio.run(adapter.execute(plan))
    result = asyncio.run(
        adapter.execute(
            plan,
            intent=approved_intent("execution.runtime", str(tmp_path.resolve()), "worker.execute"),
        )
    )
    assert result["exit_code"] == 0
