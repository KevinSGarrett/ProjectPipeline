"""Cycle 21 dispatch and worker authority regressions."""

from __future__ import annotations

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from project_pipeline.autonomy_runtime.context_validation import NATIVE_PASS, job_input_digest
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.remote_job import (
    RemoteJobController,
    RemoteJobEnvelope,
    RemoteJobResult,
)
from project_pipeline.autonomy_runtime.remote_worker_protocol import run_envelope
from project_pipeline.autonomy_runtime.ssh_dispatch import (
    SshDispatchAdapter,
    ssh_config_user_option,
)
from project_pipeline.scheduler.admission import chosen_host_admitted

NOW = datetime.now(UTC)
SHA = "f41c64d5b533ed4a329e0e431ee073dd791ee050"
TREE = "66778a1fdc0a7a8d8cf3b07f25367ed896ffca2b"
HOST = "COMFY-V4-CPU-01"
PRINCIPAL = r"comfy-v4-cpu-01\windows 11"


def _identity() -> dict[str, str]:
    return {
        "hostname": HOST,
        "principal": PRINCIPAL,
        "sid": "S-1-5-21-comfy",
        "module_sha256": "a" * 64,
    }


def _envelope(tmp_path: Path, name: str, **changes: object) -> RemoteJobEnvelope:
    workspace = tmp_path / name
    workspace.mkdir(exist_ok=True)
    values: dict[str, object] = dict(
        job_id=name,
        host_id=HOST,
        profile_id="CPU_WORKER",
        principal=PRINCIPAL,
        lease_id="LEASE-1",
        fence="fence-1",
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        input_sha256="d" * 64,
        argv=("python", r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_validation_job.py"),
        workspace=str(workspace),
        workspace_root=str(tmp_path),
        deadline_utc=NOW + timedelta(minutes=5),
        cpu_ceiling=1,
        memory_mb_ceiling=64,
        correlation_id="cycle21",
    )
    values.update(changes)
    return RemoteJobEnvelope.model_validate(values)


def test_worker_rejects_missing_host_and_wrong_sid(tmp_path: Path) -> None:
    payload = {
        "action": "execute",
        "host_id": "",
        "job_id": "blank-host",
        "argv": ["python", "-V"],
        "workspace": str(tmp_path),
        "workspace_root": str(tmp_path),
        "input_sha256": "d" * 64,
    }
    with patch(
        "project_pipeline.autonomy_runtime.remote_worker_protocol.local_runtime_identity",
        return_value=_identity(),
    ):
        missing = run_envelope(payload)
    assert missing["ok"] is False
    assert missing["reason"] == "authority_missing"
    env = _envelope(tmp_path, "wrong-sid")
    payload = env.model_dump(mode="json")
    payload["argv"] = list(env.argv)
    with patch(
        "project_pipeline.autonomy_runtime.remote_worker_protocol.local_runtime_identity",
        return_value={**_identity(), "principal": "OTHER", "sid": "S-1-5-21-other"},
    ):
        wrong = run_envelope(payload)
    assert wrong["ok"] is False
    assert wrong["reason"] == "authority_unverified"


def test_worker_requires_input_digest(tmp_path: Path) -> None:
    env = _envelope(tmp_path, "missing-input")
    payload = env.model_dump(mode="json")
    payload["argv"] = list(env.argv)
    payload["input_sha256"] = ""
    with patch(
        "project_pipeline.autonomy_runtime.remote_worker_protocol.local_runtime_identity",
        return_value=_identity(),
    ):
        result = run_envelope(payload)
    assert result["ok"] is False
    assert result["reason"] == "authority_missing"


def test_store_rejects_exit_nine_and_changed_intent(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "jobs.sqlite3")
    env = _envelope(tmp_path, "accept-auth")
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    result = RemoteJobResult(
        job_id=env.job_id,
        host_id=env.host_id,
        fence=env.fence,
        exit_code=9,
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        output_sha256="3" * 64,
    )
    controller = RemoteJobController(store=store, require_intent=True)
    rejected = controller.accept(env, result, expected_host=HOST, now=NOW)
    assert rejected["outcome"] == "REJECTED"
    assert rejected["reason"] == "nonzero_exit"
    altered = env.model_copy(update={"source_sha": "0" * 40})
    zero = result.model_copy(update={"exit_code": 0})
    changed = controller.accept(altered, zero, expected_host=HOST, now=NOW)
    assert changed["outcome"] == "REJECTED"


def test_revocation_inside_accept_transaction(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "revoke.sqlite3")
    env = _envelope(tmp_path, "revoke")
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    store.expire_fence(env.fence, now=NOW)
    result = RemoteJobResult(
        job_id=env.job_id,
        host_id=env.host_id,
        fence=env.fence,
        exit_code=0,
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        output_sha256="3" * 64,
    )
    accepted = RemoteJobController(store=store, require_intent=True).accept(
        env, result, expected_host=HOST, now=NOW
    )
    assert accepted["outcome"] == "REJECTED"
    assert accepted["reason"] == "expired_fence"


def test_concurrent_worker_claim_is_once_only(tmp_path: Path) -> None:
    env = _envelope(tmp_path, "concurrent-worker")
    payload = env.model_dump(mode="json")
    payload["argv"] = list(env.argv)
    launches: list[int] = []

    def fake_spawn(**kwargs: object) -> tuple[object, dict[str, object]]:
        launches.append(1)

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""
            pid = 7
            creation_time = "111"
            output_truncated = False

        return Completed(), {"pid": 7, "creation_time": "111", "mechanism": "fixture"}

    with (
        patch(
            "project_pipeline.autonomy_runtime.remote_worker_protocol.local_runtime_identity",
            return_value=_identity(),
        ),
        patch(
            "project_pipeline.autonomy_runtime.remote_worker_protocol._spawn_enforced",
            side_effect=fake_spawn,
        ),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        futures = [pool.submit(run_envelope, payload) for _ in range(2)]
        results = [item.result(timeout=10) for item in futures]
    assert len(launches) == 1
    assert sum(1 for item in results if item.get("ok") and not item.get("duplicate")) == 1


def test_ssh_does_not_retry_typeerror(tmp_path: Path) -> None:
    key = tmp_path / "id"
    key.write_text("not-a-secret", encoding="utf-8")
    calls: list[object] = []

    def runner(argv: list[str], **kwargs: object) -> object:
        calls.append(kwargs)
        raise TypeError("after launch")

    adapter = SshDispatchAdapter.for_machine(HOST, identity=key, runner=runner)
    caught = False
    try:
        adapter.execute(
            command=[
                "python",
                r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_validation_job.py",
            ],
            working_directory=tmp_path,
            envelope=_envelope(tmp_path, "ssh-retry").model_dump(mode="json"),
        )
    except TypeError:
        caught = True
    assert caught is True
    assert len(calls) == 1


def test_consume_context_requires_identity(tmp_path: Path) -> None:
    payload = {
        "action": "consume_context",
        "host_id": HOST,
        "job_id": "consume-unauth",
        "workspace": str(tmp_path),
        "workspace_root": str(tmp_path),
        "pack_sha256": "c" * 64,
        "argv": ["python", r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_validation_job.py"],
        "input_sha256": "d" * 64,
    }
    with patch(
        "project_pipeline.autonomy_runtime.remote_worker_protocol.local_runtime_identity",
        return_value=_identity(),
    ):
        result = run_envelope(payload)
    assert result["ok"] is False
    assert result["reason"] in {"authority_missing", "authority_unverified"}


def test_store_requires_artifact_bytes_when_contract_set(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "jobs.sqlite3")
    body = b"<testsuite tests='1'/>"
    contract = hashlib.sha256(body).hexdigest()
    env = _envelope(tmp_path, "artifact-bytes", output_contract_sha256=contract)
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    result = RemoteJobResult(
        job_id=env.job_id,
        host_id=env.host_id,
        fence=env.fence,
        exit_code=0,
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        output_sha256=contract,
    )
    controller = RemoteJobController(store=store, require_intent=True)
    missing = controller.accept(env, result, expected_host=HOST, now=NOW)
    assert missing["outcome"] == "REJECTED"
    assert missing["reason"] == "artifact_bytes_required"
    echoed = controller.accept(
        env, result, expected_host=HOST, now=NOW, artifact_bytes=b"not-the-junit"
    )
    assert echoed["reason"] == "output_tamper"
    accepted = controller.accept(env, result, expected_host=HOST, now=NOW, artifact_bytes=body)
    assert accepted["outcome"] == "ACCEPTED"


def test_store_requires_artifact_bytes_for_context_jobs(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "jobs.sqlite3")
    env = _envelope(tmp_path, "context-bytes", require_context_consumption=True)
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    result = RemoteJobResult(
        job_id=env.job_id,
        host_id=env.host_id,
        fence=env.fence,
        exit_code=0,
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        output_sha256="3" * 64,
    )
    missing = RemoteJobController(store=store, require_intent=True).accept(
        env, result, expected_host=HOST, now=NOW
    )
    assert missing["reason"] == "artifact_bytes_required"


def test_prelaunch_pack_failure_releases_claim_for_retry(tmp_path: Path) -> None:
    env = _envelope(tmp_path, "pack-retry")
    pack_sha = "c" * 64
    digest = job_input_digest(
        task_id=env.job_id,
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        pack_sha256=pack_sha,
        selection=(NATIVE_PASS,),
    )
    payload = env.model_dump(mode="json")
    payload["argv"] = list(env.argv)
    payload["require_context_consumption"] = True
    payload["pack_sha256"] = pack_sha
    payload["input_sha256"] = digest
    with patch(
        "project_pipeline.autonomy_runtime.remote_worker_protocol.local_runtime_identity",
        return_value=_identity(),
    ):
        first = run_envelope(payload)
        second = run_envelope(payload)
    assert first["ok"] is False
    assert first["reason"] == "pack_missing"
    assert second["reason"] != "unresolved_in_flight"
    assert second["reason"] == "pack_missing"


def test_failed_complete_cache_does_not_block_retry(tmp_path: Path) -> None:
    env = _envelope(tmp_path, "failed-cache")
    payload = env.model_dump(mode="json")
    payload["argv"] = list(env.argv)

    class Failed:
        returncode = 2
        stdout = "no pytest"
        stderr = "No module named pytest"
        pid = 1
        creation_time = "1"
        output_truncated = False

    class Passed:
        returncode = 0
        stdout = "ok"
        stderr = ""
        pid = 2
        creation_time = "2"
        output_truncated = False

    calls = {"n": 0}

    def fake_spawn(**kwargs: object) -> tuple[object, dict[str, object]]:
        del kwargs
        calls["n"] += 1
        if calls["n"] == 1:
            return Failed(), {"pid": 1, "creation_time": "1", "mechanism": "fixture"}
        return Passed(), {"pid": 2, "creation_time": "2", "mechanism": "fixture"}

    with (
        patch(
            "project_pipeline.autonomy_runtime.remote_worker_protocol.local_runtime_identity",
            return_value=_identity(),
        ),
        patch(
            "project_pipeline.autonomy_runtime.remote_worker_protocol._spawn_enforced",
            side_effect=fake_spawn,
        ),
    ):
        first = run_envelope(payload)
        second = run_envelope(payload)
    assert first["ok"] is False
    assert first.get("duplicate") is not True
    assert second["ok"] is True
    assert second.get("duplicate") is not True
    assert calls["n"] == 2


def test_cycle_owned_job_admits_measured_host_without_c18() -> None:
    record = {
        "source_sha": SHA,
        "source_tree": TREE,
        "hosts": {
            HOST: {
                "state": "READY",
                "freshness": "fresh",
                "observation_kind": "MEASURED",
                "observed_at_utc": NOW.isoformat(),
                "sid": "S-1-5-21-comfy",
                "principal": PRINCIPAL,
                "workspace_root": r"C:\Users\Windows 11\ProjectPipeline\jobs",
            }
        },
    }
    owned = chosen_host_admitted(
        record, HOST, expected_sha=SHA, expected_tree=TREE, now=NOW, cycle_owned=True
    )
    assert owned["ok"] is True
    production = chosen_host_admitted(
        record, HOST, expected_sha=SHA, expected_tree=TREE, now=NOW, cycle_owned=False
    )
    assert production["ok"] is False
    assert "c18_acceptance_missing" in production["failures"]


def test_scp_uses_user_option_not_user_at_host(tmp_path: Path) -> None:
    key = tmp_path / "id_ed25519"
    key.write_text("placeholder", encoding="utf-8")
    dest = tmp_path / "junit.xml"
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        dest.write_bytes(b"<testsuite tests='1'></testsuite>")
        return subprocess.CompletedProcess(argv, 0, "", "")

    adapter = SshDispatchAdapter.for_machine(HOST, identity=key)
    workspace = Path(r"C:\Users\Windows 11\ProjectPipeline\jobs")
    with patch(
        "project_pipeline.autonomy_runtime.ssh_dispatch.subprocess.run",
        side_effect=fake_run,
    ):
        payload = adapter.acquire_workspace_file(workspace, "junit.xml", dest)
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert argv[0] == "scp"
    assert ssh_config_user_option("Windows 11") in argv
    assert ssh_config_user_option("Windows 11") == 'User="Windows 11"'
    assert not any("Windows 11@" in str(item) for item in argv)
    assert "python" not in argv
    assert "-c" not in argv
    assert payload == b"<testsuite tests='1'></testsuite>"
