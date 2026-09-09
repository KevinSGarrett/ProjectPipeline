from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.confinement import (
    ConfinementError,
    canonicalize_workspace,
    confine_remote_workspace,
)
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.remote_job import RemoteJobController, RemoteJobEnvelope
from project_pipeline.autonomy_runtime.service import LocalSubprocessDispatchAdapter
from project_pipeline.autonomy_runtime.ssh_dispatch import (
    SshDispatchAdapter,
    build_ssh_argv,
    parse_worker_stdout,
    remote_command_allowed,
)
from project_pipeline.autonomy_runtime.windows_limits import (
    ResourceLimitError,
    close_job_handle,
    enforce_or_reject,
    nested_pool_env,
)
from project_pipeline.autonomy_runtime.worker_entrypoint import run_envelope
from project_pipeline.autonomy_runtime.worker_supervision import (
    recover_isolated_job,
    start_isolated_job,
)
from project_pipeline.overlay import overlay_digest

NOW = datetime(2026, 9, 8, tzinfo=UTC)
SHA = "a" * 40
TREE = "b" * 40


def _envelope(tmp_path: Path, **overrides: object) -> RemoteJobEnvelope:
    workspace = tmp_path / "job"
    workspace.mkdir(exist_ok=True)
    payload = {
        "job_id": "PP-TASK-000516",
        "host_id": "COMFY-V4-CPU-01",
        "profile_id": "cpu",
        "principal": "worker",
        "lease_id": "LEASE-AAAAAAAAAAAAAAAAAAAA",
        "fence": "1",
        "source_sha": SHA,
        "source_tree": TREE,
        "overlay_sha256": "c" * 64,
        "input_sha256": "d" * 64,
        "argv": (sys.executable, "-c", "print('ok')"),
        "workspace": str(workspace),
        "deadline_utc": NOW + timedelta(minutes=5),
        "cpu_ceiling": 1,
        "memory_mb_ceiling": 512,
        "correlation_id": "corr-c20",
        "workspace_root": str(tmp_path),
    }
    payload.update(overrides)
    return RemoteJobEnvelope.model_validate(payload)


class _RemoteMock:
    remote_host = True
    machine_id = "COMFY-V4-CPU-01"
    exit_code = 0

    def execute(self, **_kwargs: object) -> dict[str, object]:
        return {
            "exit_code": self.exit_code,
            "timed_out": False,
            "stdout_sha256": "1" * 64,
            "stderr_sha256": "2" * 64,
            "payload_sha256": "3" * 64,
        }


def test_restart_rejects_conflicting_expired_result(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "jobs.sqlite3")
    envelope = _envelope(tmp_path)
    store.persist_intent(envelope.model_dump(mode="json"), now=NOW)
    first = RemoteJobController(_RemoteMock(), store=store, require_intent=True)
    executed = first.execute(envelope, now=NOW)
    accepted = first.accept(envelope, executed["result"], expected_host=envelope.host_id, now=NOW)
    assert accepted["outcome"] == "ACCEPTED"
    first.expire_fence(envelope.fence)
    late = envelope.model_copy(update={"deadline_utc": NOW - timedelta(days=1)})
    tampered = executed["result"].model_copy(update={"output_sha256": "e" * 64})
    restarted = RemoteJobController(store=store, require_intent=True)
    replay = restarted.accept(late, tampered, expected_host=envelope.host_id, now=NOW)
    assert replay["outcome"] == "REJECTED"


def test_concurrent_duplicate_dispatch_does_not_reexecute(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "jobs.sqlite3")
    envelope = _envelope(tmp_path)
    store.persist_intent(envelope.model_dump(mode="json"), now=NOW)
    runs = {"count": 0}

    class _Counting(_RemoteMock):
        def execute(self, **_kwargs: object) -> dict[str, object]:
            runs["count"] += 1
            return super().execute()

    controller = RemoteJobController(_Counting(), store=store, require_intent=True)
    first = controller.execute(envelope, now=NOW)
    assert first["outcome"] == "EXECUTED"
    controller.accept(envelope, first["result"], expected_host=envelope.host_id, now=NOW)
    second = RemoteJobController(_Counting(), store=store, require_intent=True).execute(
        envelope, now=NOW
    )
    assert second["reason"] == "already_accepted"
    assert runs["count"] == 1


def test_nonzero_exit_and_output_tamper_are_rejected(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path, output_contract_sha256="f" * 64)

    class _Fail(_RemoteMock):
        exit_code = 1

    executed = RemoteJobController(_Fail()).execute(envelope, now=NOW)
    denied = RemoteJobController().accept(
        envelope, executed["result"], expected_host=envelope.host_id, now=NOW
    )
    assert denied["reason"] == "nonzero_exit"
    ok_envelope = envelope.model_copy(update={"output_contract_sha256": "3" * 64})
    executed_ok = RemoteJobController(_RemoteMock()).execute(ok_envelope, now=NOW)
    tamper = RemoteJobController().accept(
        ok_envelope,
        executed_ok["result"],
        expected_host=ok_envelope.host_id,
        now=NOW,
        artifact_bytes=b"nope",
    )
    assert tamper["reason"] == "output_tamper"


def test_caller_envelope_without_intent_is_rejected(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "jobs.sqlite3")
    envelope = _envelope(tmp_path)
    denied = RemoteJobController(store=store, require_intent=True).execute(envelope, now=NOW)
    assert denied["reason"] == "intent_missing"


def test_traversal_and_metacharacters_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ConfinementError):
        canonicalize_workspace(r"C:\Windows\..\pp_jobs", root=str(root))
    with pytest.raises(ConfinementError):
        canonicalize_workspace(r"C:\pp_jobs & echo AUDIT", root=str(root))
    with pytest.raises(ConfinementError):
        canonicalize_workspace(r"\\100.1.1.1\share", root=str(root))


def test_ssh_does_not_interpolate_remote_cwd(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("not-a-real-key\n", encoding="utf-8")
    argv = build_ssh_argv(
        identity=identity,
        user="kines",
        host="100.107.207.66",
        remote_argv=["hostname"],
        remote_cwd=r"C:\Users\kines\safe",
    )
    joined = " ".join(argv)
    assert "cmd" not in argv
    assert "cd /d" not in joined
    assert r"C:\Users\kines\safe" not in joined
    assert remote_command_allowed(("python", r"C:\Users\kines\pp_jobs\job.py")) is False
    assert remote_command_allowed(("hostname",)) is True


def test_nested_pools_are_bound() -> None:
    env = nested_pool_env(2)
    assert env["OMP_NUM_THREADS"] == "2"
    assert env["OPENBLAS_NUM_THREADS"] == "2"


def test_secret_argv_is_rejected(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "jobs.sqlite3")
    envelope = _envelope(
        tmp_path, argv=(sys.executable, "-c", "print('api_key=sk-abcdefghijklmnop')")
    )
    denied = store.persist_intent(envelope.model_dump(mode="json"), now=NOW)
    assert denied["reason"] == "secret_in_envelope"
    executed = RemoteJobController(store=store, require_intent=True).execute(envelope, now=NOW)
    assert executed["reason"] in {"secret_in_argv", "intent_missing"}


def test_worker_stdout_pid_is_parsed() -> None:
    parsed = parse_worker_stdout('noise\n{"ok": true, "pid": 4242, "exit_code": 0}\n')
    assert parsed["pid"] == 4242


def test_local_adapter_timeout_does_not_raise_unbound_pid(tmp_path: Path) -> None:
    adapter = LocalSubprocessDispatchAdapter()
    payload = adapter.execute(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        working_directory=tmp_path,
        timeout_seconds=1,
    )
    assert payload["timed_out"] is True
    assert payload["exit_code"] == 124
    assert payload["remote_pid"] == ""


def test_local_isolated_worker_loss_recovers(tmp_path: Path) -> None:
    child = start_isolated_job(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        workspace=tmp_path,
    )
    recovered = recover_isolated_job(child)
    assert recovered["recovered"] is True
    assert recovered["running"] is False
    assert child.poll() is not None


def test_ssh_kill_stdin_uses_action_kill(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("placeholder", encoding="utf-8")
    captured: dict[str, str] = {}

    def _runner(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["input"] = str(kwargs.get("input") or "")
        return subprocess.CompletedProcess(
            ["ssh"], 0, '{"ok": true, "pid": 4242, "killed": true, "phase": "kill"}', ""
        )

    adapter = SshDispatchAdapter(identity=identity, runner=_runner)
    payload = adapter.kill_pid(4242, workspace=tmp_path)
    assert '"action": "kill"' in captured["input"]
    assert '"pid": 4242' in captured["input"]
    assert payload["exit_code"] == 0
    assert payload["remote_pid"] == "4242"


def test_worker_side_dedup(tmp_path: Path) -> None:
    workspace = tmp_path / "job"
    workspace.mkdir()
    payload = {
        "argv": [sys.executable, "-c", "print('once')"],
        "workspace": str(workspace),
        "job_id": "PP-TASK-000516",
        "input_sha256": "d" * 64,
    }
    first = run_envelope(payload)
    second = run_envelope(payload)
    assert first["ok"] is True
    assert second["duplicate"] is True


def test_enforce_or_reject_creates_job_object() -> None:
    if sys.platform != "win32":
        with pytest.raises(ResourceLimitError, match="job_object_unavailable"):
            enforce_or_reject(cpu_ceiling=1, memory_mb_ceiling=256, deadline_seconds=5)
        return
    limits = enforce_or_reject(cpu_ceiling=1, memory_mb_ceiling=256, deadline_seconds=5)
    assert limits["ok"] is True
    assert limits["mechanism"] == "windows_job_object"
    close_job_handle(int(limits["handle"]))


def test_overlay_digest_changes_when_bytes_change(tmp_path: Path) -> None:
    overlay = tmp_path / "overlay"
    (overlay / "instructions").mkdir(parents=True)
    target = overlay / "instructions" / "pack.txt"
    target.write_text("one", encoding="utf-8")
    first = overlay_digest(overlay)
    target.write_text("two", encoding="utf-8")
    assert overlay_digest(overlay) != first


def test_remote_workspace_must_stay_under_allowed_root() -> None:
    allowed = r"C:\Users\kines\ProjectPipeline\jobs"
    assert confine_remote_workspace(allowed + r"\out", allowed_root=allowed) == allowed + r"\out"
    with pytest.raises(ConfinementError, match="workspace_outside_root"):
        confine_remote_workspace(r"C:\Windows\Temp", allowed_root=allowed)
    with pytest.raises(ConfinementError, match="workspace_outside_root"):
        confine_remote_workspace(r"C:\Users\kines\pp_jobs", allowed_root=allowed)


def test_ssh_stdin_carries_job_identity(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("placeholder", encoding="utf-8")
    captured: dict[str, str] = {}

    def _runner(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["input"] = str(kwargs.get("input") or "")
        return subprocess.CompletedProcess(["ssh"], 0, '{"ok": true, "exit_code": 0}', "")

    adapter = SshDispatchAdapter(identity=identity, runner=_runner)
    adapter.execute(
        command=["hostname"],
        working_directory=tmp_path,
        job_id="PP-TASK-000516",
        input_sha256="d" * 64,
    )
    assert '"job_id": "PP-TASK-000516"' in captured["input"]
    assert '"input_sha256": "' + ("d" * 64) + '"' in captured["input"]
