"""Cycle 21 remote execution, confinement, and bounded output."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from project_pipeline.autonomy_runtime import remote_worker_protocol as worker_protocol
from project_pipeline.autonomy_runtime.remote_worker_protocol import (
    _pid_is_owned,
    module_sha256,
    run_envelope,
)
from project_pipeline.autonomy_runtime.worker_allowlist import (
    remote_command_allowed,
    worker_launch_argv,
)

NOW = datetime.now(UTC)
HOST = "COMFY-V4-CPU-01"
PRINCIPAL = r"comfy-v4-cpu-01\windows 11"


def _identity() -> dict[str, str]:
    return {
        "hostname": HOST,
        "principal": PRINCIPAL,
        "sid": "S-1-5-21-comfy",
        "module_sha256": module_sha256(worker_protocol.__file__),
        "source_sha": "f41c64d5b533ed4a329e0e431ee073dd791ee050",
        "source_tree": "66778a1fdc0a7a8d8cf3b07f25367ed896ffca2b",
    }


def test_comfy_ssh_transport_argv_has_no_spaces() -> None:
    argv = worker_launch_argv(HOST)
    assert argv[0] == "python"
    assert all(" " not in item for item in argv)
    assert remote_command_allowed(argv) is True


def test_rejects_traversal_and_unapproved_scripts() -> None:
    assert remote_command_allowed(("python", r"C:\unapproved\arbitrary.py")) is False
    assert (
        remote_command_allowed(("python", r"C:\Users\Windows 11\ProjectPipeline\jobs\..\secret.py"))
        is False
    )
    assert (
        remote_command_allowed(
            ("python", r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_validation_job.py")
        )
        is True
    )


def test_kill_requires_principal_and_filetime() -> None:
    recorded = {
        "job_id": "owned",
        "fence": "f1",
        "principal": PRINCIPAL,
        "pid": 424242,
        "child_pid": 424242,
        "creation_time": "111",
    }
    assert (
        _pid_is_owned(
            recorded,
            job_id="owned",
            fence="f1",
            principal="",
            pid_i=424242,
            creation_time="111",
        )
        is False
    )
    assert (
        _pid_is_owned(
            recorded,
            job_id="owned",
            fence="f1",
            principal=PRINCIPAL,
            pid_i=424242,
            creation_time="",
        )
        is False
    )
    with patch(
        "project_pipeline.autonomy_runtime.remote_worker_protocol.process_creation_filetime",
        return_value="RECYCLED_NEW_CREATION",
    ):
        assert (
            _pid_is_owned(
                recorded,
                job_id="owned",
                fence="f1",
                principal=PRINCIPAL,
                pid_i=424242,
                creation_time="111",
            )
            is False
        )


def test_kill_payload_without_identity_is_rejected(tmp_path: Path) -> None:
    result = run_envelope({"action": "kill", "pid": 424242})
    assert result["ok"] is False
    assert result["reason"] == "ownership_identity_required"


def test_cache_does_not_reuse_changed_fence(tmp_path: Path) -> None:
    workspace = tmp_path / "cache"
    workspace.mkdir()
    payload = {
        "action": "execute",
        "job_id": "cache-job",
        "host_id": HOST,
        "profile_id": "CPU_WORKER",
        "principal": PRINCIPAL,
        "lease_id": "LEASE-1",
        "fence": "old-fence",
        "source_sha": "f41c64d5b533ed4a329e0e431ee073dd791ee050",
        "source_tree": "66778a1fdc0a7a8d8cf3b07f25367ed896ffca2b",
        "overlay_sha256": "c" * 64,
        "input_sha256": "d" * 64,
        "deadline_utc": (NOW + timedelta(minutes=5)).isoformat(),
        "cpu_ceiling": 1,
        "memory_mb_ceiling": 64,
        "workspace": str(workspace),
        "workspace_root": str(tmp_path),
        "argv": ["python", r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_validation_job.py"],
        "lease_grant": {
            "lease_id": "LEASE-1",
            "fence": "old-fence",
            "job_id": "cache-job",
            "host_id": HOST,
            "status": "ACTIVE",
            "source_sha": "f41c64d5b533ed4a329e0e431ee073dd791ee050",
            "source_tree": "66778a1fdc0a7a8d8cf3b07f25367ed896ffca2b",
            "overlay_sha256": "c" * 64,
        },
    }

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""
        pid = 7
        creation_time = "111"
        output_truncated = False

    with (
        patch(
            "project_pipeline.autonomy_runtime.remote_worker_protocol.local_runtime_identity",
            return_value=_identity(),
        ),
        patch(
            "project_pipeline.autonomy_runtime.remote_worker_protocol._spawn_enforced",
            return_value=(Completed(), {"pid": 7, "creation_time": "111", "mechanism": "fixture"}),
        ),
    ):
        first = run_envelope(payload)
        payload["fence"] = "NEW_FENCE"
        second = run_envelope(payload)
    assert first.get("duplicate") is False
    assert second.get("duplicate") is not True or second.get("fence") == "NEW_FENCE"
