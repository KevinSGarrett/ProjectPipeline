from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from project_pipeline.agent_router.adapters import ProviderAdapterError
from project_pipeline.autonomy_runtime import cursor_cli_qualification as cursor_cli_module
from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    ARTIFACT_NAME,
    IDEMPOTENCY_KEY,
    _write_expected_artifact,
    locate_cursor_cli_launch,
    qualify_cursor_cli_provider,
    remove_disposable_workspace,
)
from project_pipeline.lifecycle import attestation_recovery as attestation_recovery_module
from project_pipeline.lifecycle.attestation_recovery import (
    EXPECTED_PUBLIC_ATTESTATION_SHA256,
    PUBLIC_ATTESTATION_REF,
    PUBLIC_QUALIFICATION_REF,
    CurrentAttestationPolicy,
    recover_and_restore,
    sha256_bytes,
)
from tests.pp379_recovery_support import (
    copy_agent_registry,
    durable_dir,
    isolated_repo,
    source_root,
    write_json,
)


def _cli_result(stdout: dict[str, object] | None = None) -> CompletedProcess[bytes]:
    payload = stdout or {
        "type": "result",
        "result": "qualification artifact written",
        "session_id": "sess-pp384",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    return CompletedProcess(
        args=["agent"],
        returncode=0,
        stdout=json.dumps(payload).encode("utf-8"),
        stderr=b"",
    )


def _success_runner(workspace: Path):
    def runner(*args: object, **kwargs: object) -> CompletedProcess[bytes]:
        cwd = Path(str(kwargs.get("cwd") or (workspace / "cursor-cli-qualification")))
        _write_expected_artifact(cwd, IDEMPOTENCY_KEY)
        return _cli_result()

    return runner


def _repo_with_evidence(tmp_path: Path) -> Path:
    repo = isolated_repo(tmp_path)
    recover_and_restore(
        repository_root=repo,
        source_root=source_root(),
        durable_dir=durable_dir(),
        verification_dir=tmp_path / "restore-verify",
        apply=True,
    )
    return repo


def test_missing_public_with_recoverable_durable_restores_and_can_pass(tmp_path: Path) -> None:
    repo = isolated_repo(tmp_path)
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
    )
    assert report["outcome"] == "PASSED"
    assert (repo / PUBLIC_ATTESTATION_REF).is_file()
    assert sha256_bytes((repo / PUBLIC_ATTESTATION_REF).read_bytes()) == (
        EXPECTED_PUBLIC_ATTESTATION_SHA256
    )


def test_missing_evidence_without_recoverable_source_fails(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    copy_agent_registry(repo)
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        durable_dir=tmp_path / "absent-durable",
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
    )
    assert report["outcome"] == "FAILED"
    assert "missing evidence with no recoverable source" in report["reasons"]


def test_wrong_bytes_at_correct_path_cannot_pass(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)
    (repo / PUBLIC_ATTESTATION_REF).write_text(
        '{"approved":true,"project_id":"PROJECT-PIPELINE"}',
        encoding="utf-8",
    )
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
    )
    assert report["outcome"] == "FAILED"


def test_digest_mismatch_and_identity_mismatch_fail(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
        policy=CurrentAttestationPolicy(project_id="OTHER-PROJECT"),
    )
    assert report["outcome"] == "FAILED"


def test_stale_timestamp_under_finite_policy_fails(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
        policy=CurrentAttestationPolicy(max_age_hours=1),
    )
    assert report["outcome"] == "FAILED"
    assert "stale timestamp under a finite policy" in report["reasons"]


def test_invalid_timestamp_fails(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)
    durable = tmp_path / "durable-invalid"
    durable.mkdir()
    payload = json.loads((durable_dir() / "privacy_attestation.json").read_text(encoding="utf-8"))
    payload["approved_at_utc"] = "not-a-timestamp"
    write_json(durable / "privacy_attestation.json", payload)
    qualification = json.loads(
        (durable_dir() / "provider_qualification.json").read_text(encoding="utf-8")
    )
    qualification["verified_at_utc"] = datetime.now(UTC).isoformat()
    write_json(durable / "provider_qualification.json", qualification)
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable,
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
        policy=CurrentAttestationPolicy(max_age_hours=24),
    )
    assert report["outcome"] == "FAILED"
    assert "invalid timestamp" in report["reasons"]


def test_unqualified_provider_fails(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)
    providers = json.loads(
        (repo / "config" / "agents" / "providers.json").read_text(encoding="utf-8")
    )
    models = json.loads((repo / "config" / "agents" / "models.json").read_text(encoding="utf-8"))
    write_json(
        repo / "config" / "agents" / "providers.json",
        [item for item in providers if item.get("provider_id") != "provider:cursor-cli"],
    )
    write_json(
        repo / "config" / "agents" / "models.json",
        [item for item in models if item.get("provider_id") != "provider:cursor-cli"],
    )
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
    )
    assert report["outcome"] == "FAILED"
    assert "unqualified_provider" in report["reasons"]


def test_executable_unavailable_is_blocked_external(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)

    def missing_runner(*args: object, **kwargs: object) -> CompletedProcess[bytes]:
        raise ProviderAdapterError("missing", kind="UNAVAILABLE", provider_state="UNAVAILABLE")

    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=missing_runner,
        executable="agent",
    )
    assert report["outcome"] == "BLOCKED_EXTERNAL"


def test_dispatch_timeout_is_blocked_external(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)

    def timeout_runner(*args: object, **kwargs: object) -> CompletedProcess[bytes]:
        raise ProviderAdapterError(
            "timeout", kind="TIMEOUT", retryable=True, provider_state="DEGRADED"
        )

    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=timeout_runner,
        executable="agent",
    )
    assert report["outcome"] == "BLOCKED_EXTERNAL"


def test_forged_provider_identity_fails(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)

    def bad_payload(*args: object, **kwargs: object) -> CompletedProcess[bytes]:
        return CompletedProcess(
            args=["agent"], returncode=0, stdout=b'{"type":"error"}', stderr=b""
        )

    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=bad_payload,
        executable="agent",
    )
    assert report["outcome"] == "FAILED"


def test_out_of_scope_mutation_fails(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)

    def mutating_runner(*args: object, **kwargs: object) -> CompletedProcess[bytes]:
        workspace = tmp_path / "runtime" / "cursor-cli-qualification"
        _write_expected_artifact(workspace, IDEMPOTENCY_KEY)
        (workspace / "extra.txt").write_text("nope", encoding="utf-8")
        return _cli_result()

    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=mutating_runner,
        executable="agent",
    )
    assert report["outcome"] == "FAILED"
    assert "out-of-scope mutation" in report["reasons"]


def test_idempotent_replay_does_not_rewrite(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)
    calls = {"n": 0}

    def replay_runner(*args: object, **kwargs: object) -> CompletedProcess[bytes]:
        workspace = tmp_path / "runtime" / "cursor-cli-qualification"
        calls["n"] += 1
        _write_expected_artifact(workspace, IDEMPOTENCY_KEY)
        if calls["n"] > 1:
            (workspace / ARTIFACT_NAME).write_text('{"conflict":true}', encoding="utf-8")
        return _cli_result()

    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=replay_runner,
        executable="agent",
    )
    assert report["outcome"] == "PASSED"
    assert calls["n"] == 1
    replay = next(item for item in report["phases"] if item["phase"] == "REPLAY")
    assert replay["observations"]["ok"] is True


def test_conflicting_replay_fails(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)

    def conflicting_runner(*args: object, **kwargs: object) -> CompletedProcess[bytes]:
        workspace = tmp_path / "runtime" / "cursor-cli-qualification"
        _write_expected_artifact(workspace, "other-key")
        return _cli_result()

    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=conflicting_runner,
        executable="agent",
    )
    assert report["outcome"] == "FAILED"
    assert "readback_failed" in report["reasons"]


def test_conflicting_replay_digest_mismatch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_with_evidence(tmp_path)
    original = cursor_cli_module._dispatch_via_registered_adapter
    calls = {"n": 0}

    def mutating_dispatch(**kwargs: object):
        result = original(**kwargs)
        calls["n"] += 1
        if calls["n"] > 1:
            workspace = Path(str(kwargs["workspace"]))
            (workspace / ARTIFACT_NAME).write_text('{"conflict":true}', encoding="utf-8")
        return result

    monkeypatch.setattr(cursor_cli_module, "_dispatch_via_registered_adapter", mutating_dispatch)
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
    )
    assert report["outcome"] == "FAILED"
    assert "conflicting replay" in report["reasons"]


def test_successful_dispatch_and_replay_and_cleanup(tmp_path: Path) -> None:
    repo = _repo_with_evidence(tmp_path)
    workspace_parent = tmp_path / "runtime"
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=workspace_parent,
        source_root=source_root(),
        durable_dir=durable_dir(),
        runner=_success_runner(workspace_parent),
        executable="agent",
    )
    assert report["outcome"] == "PASSED"
    assert not (workspace_parent / "cursor-cli-qualification").exists()
    encoded = json.dumps(report)
    assert "HUMAN_REQUIRED" not in encoded
    assert "operator session" not in encoded
    assert "await human" not in encoded


def test_copying_arbitrary_json_cannot_pass_pp384(tmp_path: Path) -> None:
    repo = isolated_repo(tmp_path)
    write_json(
        repo / PUBLIC_ATTESTATION_REF,
        {
            "project_id": "PROJECT-PIPELINE",
            "provider_id": "provider:cursor-cli",
            "scope": "local-governed-phase1",
            "approved": True,
            "approved_at_utc": "2026-08-16T22:00:00+00:00",
        },
    )
    write_json(
        repo / PUBLIC_QUALIFICATION_REF,
        {
            "project_id": "PROJECT-PIPELINE",
            "provider_id": "provider:cursor-cli",
            "scope": "local-governed-phase1",
            "qualified": True,
            "verified_at_utc": "2026-08-16T22:00:00+00:00",
        },
    )
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        durable_dir=durable_dir(),
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
    )
    assert report["outcome"] != "PASSED"


def test_worktree_without_repo_durable_uses_canonical_private_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(attestation_recovery_module, "DEFAULT_DURABLE_DIR", durable_dir())
    repo = _repo_with_evidence(tmp_path)
    repo_durable = repo / ".local" / "state" / "takeover" / "privacy_attestation.json"
    assert not repo_durable.is_file()
    report = qualify_cursor_cli_provider(
        repository_root=repo,
        disposable_root=tmp_path / "runtime",
        runner=_success_runner(tmp_path / "runtime"),
        executable="agent",
    )
    assert report["outcome"] == "PASSED"
    validation = next(item for item in report["phases"] if item["phase"] == "EVIDENCE_VALIDATION")
    durable_paths = {
        Path(artifact["durable_record_path"])
        for artifact in validation["observations"]["artifacts"]
    }
    assert all(path.parent == durable_dir() for path in durable_paths)


def test_locate_wsl_agent_survives_status_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(name: str) -> str | None:
        if name in {"wsl.exe", "wsl"}:
            return r"C:\Windows\System32\wsl.exe"
        return None

    def fake_run(args: object, **kwargs: object) -> CompletedProcess[bytes]:
        argv = [str(item) for item in list(args)]  # type: ignore[arg-type]
        if "--list" in argv:
            return CompletedProcess(argv, 0, stdout=b"Cursor-Agent-WSL1\n", stderr=b"")
        if "-lc" in argv:
            return CompletedProcess(
                argv, 0, stdout=b"/home/kevin/.local/bin/cursor-agent\n", stderr=b""
            )
        if "--version" in argv:
            return CompletedProcess(argv, 0, stdout=b"2026.08.11-e8db854\n", stderr=b"")
        if "status" in argv:
            raise subprocess.TimeoutExpired(argv, 30)
        return CompletedProcess(argv, 1, stdout=b"", stderr=b"")

    monkeypatch.setattr(cursor_cli_module.shutil, "which", fake_which)
    monkeypatch.setattr(cursor_cli_module.subprocess, "run", fake_run)
    launch = locate_cursor_cli_launch()
    assert launch is not None
    assert launch["execution_mode"] == "WSL"
    assert launch["distribution"] == "Cursor-Agent-WSL1"
    assert launch["executable"] == "/home/kevin/.local/bin/cursor-agent"
    assert launch["status_timed_out"] is True
    assert launch["authenticated"] is None


def test_locate_skips_distro_when_status_fails_without_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(name: str) -> str | None:
        if name in {"wsl.exe", "wsl"}:
            return r"C:\Windows\System32\wsl.exe"
        return None

    def fake_run(args: object, **kwargs: object) -> CompletedProcess[bytes]:
        argv = [str(item) for item in list(args)]  # type: ignore[arg-type]
        if "--list" in argv:
            return CompletedProcess(argv, 0, stdout=b"BadDistro\nGoodDistro\n", stderr=b"")
        distro = argv[argv.index("-d") + 1] if "-d" in argv else ""
        if "-lc" in argv:
            return CompletedProcess(
                argv, 0, stdout=f"/home/{distro}/cursor-agent\n".encode(), stderr=b""
            )
        if "--version" in argv:
            return CompletedProcess(argv, 0, stdout=b"2026.08.11-e8db854\n", stderr=b"")
        if "status" in argv:
            code = 1 if distro == "BadDistro" else 0
            return CompletedProcess(argv, code, stdout=b"", stderr=b"")
        return CompletedProcess(argv, 1, stdout=b"", stderr=b"")

    monkeypatch.setattr(cursor_cli_module.shutil, "which", fake_which)
    monkeypatch.setattr(cursor_cli_module.subprocess, "run", fake_run)
    launch = locate_cursor_cli_launch()
    assert launch is not None
    assert launch["distribution"] == "GoodDistro"
    assert launch["executable"] == "/home/GoodDistro/cursor-agent"
    assert launch["authenticated"] is True
    assert launch["status_timed_out"] is False


def test_remove_workspace_retries_locked_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "locked-ws"
    workspace.mkdir()
    (workspace / "artifact.json").write_text("{}", encoding="utf-8")
    attempts = {"n": 0}
    real_rmtree = shutil.rmtree

    def flaky(path: object, *args: object, **kwargs: object) -> None:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("WinError 32")
        real_rmtree(path)

    monkeypatch.setattr(cursor_cli_module.shutil, "rmtree", flaky)
    monkeypatch.setattr(cursor_cli_module.time, "sleep", lambda _seconds: None)
    assert remove_disposable_workspace(workspace, attempts=5) is True
    assert not workspace.exists()
    assert attempts["n"] >= 3


def test_remove_workspace_falls_back_to_wsl_rm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "wsl-ws"
    workspace.mkdir()
    (workspace / "artifact.json").write_text("{}", encoding="utf-8")

    real_rmtree = shutil.rmtree

    def always_locked(path: object, *args: object, **kwargs: object) -> None:
        raise OSError("WinError 32")

    def fake_which(name: str) -> str | None:
        if "wsl" in name:
            return r"C:\Windows\System32\wsl.exe"
        return None

    def fake_run(args: object, **kwargs: object) -> CompletedProcess[bytes]:
        argv = [str(item) for item in list(args)]  # type: ignore[arg-type]
        assert argv[:4] == [r"C:\Windows\System32\wsl.exe", "--", "rm", "-rf"]
        assert argv[-1] == "/mnt/c/tmp/wsl-ws"
        real_rmtree(workspace)
        return CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(cursor_cli_module.shutil, "rmtree", always_locked)
    monkeypatch.setattr(cursor_cli_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(cursor_cli_module.shutil, "which", fake_which)
    monkeypatch.setattr(
        cursor_cli_module,
        "_windows_path_to_wsl",
        lambda _path: "/mnt/c/tmp/wsl-ws",
    )
    monkeypatch.setattr(cursor_cli_module.subprocess, "run", fake_run)
    assert remove_disposable_workspace(workspace, attempts=2) is True
    assert not workspace.exists()
