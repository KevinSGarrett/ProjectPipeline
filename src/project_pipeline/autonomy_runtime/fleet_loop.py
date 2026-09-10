"""Persistent Director → Control → dispatch → verify → next-work loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.confinement import REMOTE_JOB_WORKSPACES
from project_pipeline.autonomy_runtime.context_validation import job_input_digest
from project_pipeline.autonomy_runtime.dispatch_workflow import DispatchWorkflow
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore, digest_bytes
from project_pipeline.autonomy_runtime.lifecycle import FleetLifecycleJournal
from project_pipeline.autonomy_runtime.observation_eval import evaluate_observation
from project_pipeline.autonomy_runtime.remote_job import RemoteJobEnvelope
from project_pipeline.autonomy_runtime.service import LocalSubprocessDispatchAdapter
from project_pipeline.autonomy_runtime.ssh_dispatch import (
    COMFY_MACHINE_ID,
    COMFY_SSH_USER,
    COMFY_TAILNET_IPV4,
    XEON_MACHINE_ID,
    XEON_SSH_USER,
    XEON_TAILNET_IPV4,
    SshDispatchAdapter,
    job_stdout_metrics,
)
from project_pipeline.autonomy_runtime.worker_allowlist import (
    CYCLE_OWNED_VALIDATION_JOBS,
    REMOTE_HOLD_SCRIPTS,
    REMOTE_JOB_SCRIPTS,
)
from project_pipeline.command_center.autonomy_director import (
    PersistentAutonomyDirector,
    default_state_path,
    evaluate_live_control,
)
from project_pipeline.configuration import load_runtime_configuration
from project_pipeline.domain.control import ReadinessState
from project_pipeline.domain.requirements import ImplementationState, RequirementDisposition
from project_pipeline.jira import load_issues
from project_pipeline.overlay import bound_overlay, control_input_root, inspect_source_identity
from project_pipeline.requirements import load_requirement_catalog
from project_pipeline.scheduler.admission import (
    load_admission_record,
    measured_host_record,
    observation_admission_record,
    write_admission_record,
)
from project_pipeline.scheduler.fleet import MachineProfile
from project_pipeline.scheduler.host_observation import (
    apply_inventory_observation,
    declared_profiles,
    measure_remote_inventory,
)
from project_pipeline.scheduler.persistence import SchedulerStore

HISTORICAL_NOT_NEW_WORK = frozenset({"PP-TASK-000384"})
STRUCTURAL_PARENTS = frozenset({"PP-STORY-000065", "PP-STORY-000396"})
NO_READY_OUTCOME = "no_executable_leaf_ready"
CYCLE21_HOST_JOBS = {
    XEON_MACHINE_ID: "PP-TASK-000990",
    COMFY_MACHINE_ID: "PP-TASK-000991",
}
_IMPLEMENTED_ISSUE_STATES = {
    ImplementationState.IMPLEMENTED.value,
    ImplementationState.MOCK_VERIFIED.value,
    ImplementationState.LIVE_VERIFIED.value,
}
_COMPLETE_REQUIREMENT_STATES = {
    *_IMPLEMENTED_ISSUE_STATES,
    ImplementationState.BLOCKED_EXTERNAL.value,
}


def is_executable_job(task_id: str) -> bool:
    if task_id in HISTORICAL_NOT_NEW_WORK or task_id in STRUCTURAL_PARENTS:
        return False
    return task_id.startswith("PP-TASK-")


def duplicate_work_audit(root: Path) -> dict[str, Any]:
    """Flag implemented issues whose accepted requirements are still incomplete."""

    issues = load_issues(root)
    requirements = load_requirement_catalog(root)
    incomplete = {
        str(item.get("requirement_id") or "")
        for item in requirements
        if item.get("disposition") == RequirementDisposition.ACCEPTED.value
        and item.get("implementation_state") not in _COMPLETE_REQUIREMENT_STATES
        and item.get("requirement_id")
    }
    findings: list[dict[str, Any]] = []
    for issue in issues:
        linked = {str(item) for item in (issue.get("requirement_ids") or []) if item}
        overlap = sorted(linked & incomplete)
        if not overlap:
            continue
        if issue.get("implementation_state") not in _IMPLEMENTED_ISSUE_STATES:
            continue
        findings.append(
            {
                "issue_id": issue.get("local_id"),
                "implementation_state": issue.get("implementation_state"),
                "requirement_ids": overlap,
                "reason": "implemented_issue_incomplete_requirement",
            }
        )
    return {
        "incomplete_requirements": sorted(incomplete),
        "findings": findings,
    }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def useful_argv(
    root: Path,
    task_id: str,
    *,
    remote: bool = False,
    machine_id: str | None = None,
) -> tuple[str, ...]:
    artifact = f"{task_id}.json"
    if remote:
        script = REMOTE_JOB_SCRIPTS.get(machine_id or XEON_MACHINE_ID)
        if not script:
            raise ValueError(f"no remote useful-job script for {machine_id}")
        return ("python", script, "--job-id", task_id, "--output", artifact)
    script = root.resolve() / "scripts" / "cycle21_validation_job.py"
    return (sys.executable, str(script), "--job-id", task_id, "--output", artifact)


def observation_ready_task_ids(
    root: Path, database: Path | None = None, *, live_ssh: bool
) -> list[str]:
    del live_ssh
    return control_ready_task_ids(root, database)


def select_two_useful_jobs(ready: list[str], *, blocked: str | None = None) -> dict[str, Any]:
    independent = [item for item in ready if item != blocked and is_executable_job(item)]
    selected = independent[:2]
    skipped = [item for item in ready if item != blocked and item not in independent]
    return {
        "selected": selected,
        "blocked": blocked,
        "blocked_reason": None if blocked is None else "dependent_lane_preserved",
        "skipped_structural": skipped,
    }


def cycle_owned_validation_jobs(profiles: tuple[MachineProfile, ...]) -> list[str]:
    measured = {
        item.machine_id for item in profiles if item.observation_kind == "MEASURED" and item.sid
    }
    return [job_id for machine_id, job_id in CYCLE21_HOST_JOBS.items() if machine_id in measured]


def _machine_for_task(
    task_id: str,
    profiles: tuple[MachineProfile, ...],
    *,
    index: int,
    remote: bool,
) -> str:
    by_id = {
        item.machine_id: item
        for item in profiles
        if item.observation_kind == "MEASURED" or not remote
    }
    if task_id == CYCLE21_HOST_JOBS.get(XEON_MACHINE_ID):
        return XEON_MACHINE_ID
    if task_id == CYCLE21_HOST_JOBS.get(COMFY_MACHINE_ID):
        return COMFY_MACHINE_ID
    ordered = [item for item in (XEON_MACHINE_ID, COMFY_MACHINE_ID) if item in by_id]
    if not ordered:
        ordered = [item.machine_id for item in profiles] or [XEON_MACHINE_ID]
    return ordered[index % len(ordered)]


def _bind_adapter(adapter: Any, machine_id: str) -> Any:
    if isinstance(adapter, SshDispatchAdapter):
        return SshDispatchAdapter.for_machine(machine_id)
    return adapter


def _enrich_dispatched(
    task_id: str,
    dispatched: dict[str, Any],
    host_id: str,
    *,
    adapter: Any = None,
    workspace: Path | None = None,
    acquired_root: Path | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"task_id": task_id, **dispatched, "host_id": host_id}
    executed = dispatched.get("executed") if isinstance(dispatched.get("executed"), dict) else {}
    stdout = str(executed.get("stdout") or "")
    metrics = job_stdout_metrics(stdout)
    for key in ("tests_run", "collected", "artifact_sha256", "junit_sha256"):
        if item.get(key) in (None, "", 0, "0"):
            value = metrics.get(key) or executed.get(key) or dispatched.get(key)
            if value not in (None, "", 0, "0"):
                item[key] = value
    acquire = getattr(adapter, "acquire_workspace_file", None)
    job_workspace = workspace or Path(str(executed.get("working_directory") or ""))
    if acquired_root is not None and callable(acquire) and job_workspace:
        dest = Path(acquired_root) / host_id / task_id / "junit.xml"
        payload = acquire(job_workspace, "junit.xml", dest)
        if payload:
            digest = digest_bytes(payload)
            item["acquired_junit_path"] = str(dest)
            item["artifact_sha256"] = digest
            item["junit_sha256"] = digest
    return item


def control_ready_task_ids(root: Path, database: Path | None = None) -> list[str]:
    snapshot = evaluate_live_control(root, database_path=database)
    director = PersistentAutonomyDirector(default_state_path(root))
    ready = list(director._eligible_ready(snapshot))
    return [item for item in ready if is_executable_job(item)]


def blocked_dependent_lane(root: Path, database: Path | None = None) -> str | None:
    snapshot = evaluate_live_control(root, database_path=database)
    waiting = [
        item.task_id
        for item in snapshot.readiness
        if item.state is ReadinessState.WAITING_DEPENDENCIES
    ]
    return waiting[0] if waiting else None


def run_loop(
    *,
    root: Path,
    database: Path,
    ready: list[str],
    blocked: str | None,
    profiles: tuple[MachineProfile, ...],
    adapter: Any,
    workspace: Path,
    workspace_root: Path,
    source_sha: str,
    source_tree: str,
    overlay_sha256: str,
    principal: str,
    now: datetime | None = None,
    journal: FleetLifecycleJournal | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    jobs = select_two_useful_jobs(ready, blocked=blocked)
    if not jobs["selected"]:
        return _loop_result(
            jobs,
            root=root,
            now=now,
            results=[],
            next_job=None,
            reason="no_executable_leaf_ready",
            duplicate_work_audit=duplicate_work_audit(root),
        )
    with SchedulerStore(database, root) as store:
        workflow = DispatchWorkflow(
            store=store,
            jobs=FleetJobStore(database.with_name("fleet_jobs.sqlite3")),
            profiles=profiles,
            admission_path=database.with_name("fleet_admission.json"),
            source_sha=source_sha,
            source_tree=source_tree,
            overlay_sha256=overlay_sha256,
            adapter_factory=lambda machine_id: _bind_adapter(adapter, str(machine_id)),
            journal=journal or FleetLifecycleJournal(database.with_name("fleet_lifecycle.sqlite3")),
        )
        results = []
        remote = bool(getattr(adapter, "remote_host", False))
        by_id = {item.machine_id: item for item in profiles}
        for index, task_id in enumerate(jobs["selected"]):
            host_id = _machine_for_task(task_id, profiles, index=index, remote=remote)
            chosen_profile = by_id.get(host_id)
            host_principal = (
                str(chosen_profile.principal) if chosen_profile is not None else principal
            )
            job_workspace = (
                Path(REMOTE_JOB_WORKSPACES.get(host_id, str(workspace))) if remote else workspace
            )
            bind_root = str(job_workspace) if remote else str(workspace_root)
            argv = useful_argv(root, task_id, remote=remote, machine_id=host_id)
            host_adapter = _bind_adapter(adapter, host_id)
            dispatched = workflow.dispatch(
                task_id=task_id,
                holder_id="actor:fleet-loop",
                argv=argv,
                workspace=str(job_workspace),
                workspace_root=bind_root,
                principal=host_principal,
                input_sha256=job_input_digest(
                    task_id=task_id,
                    source_sha=source_sha,
                    source_tree=source_tree,
                    overlay_sha256=overlay_sha256,
                    pack_sha256=overlay_sha256,
                    selection=argv,
                ),
                now=now,
                adapter=host_adapter,
                machine_id=host_id if remote else None,
            )
            results.append(
                _enrich_dispatched(
                    task_id,
                    dispatched,
                    host_id,
                    adapter=host_adapter,
                    workspace=job_workspace,
                    acquired_root=Path(workspace_root) / "acquired",
                )
            )
        remaining_ready = [
            item
            for item in ready
            if item not in jobs["selected"] and item != blocked and is_executable_job(item)
        ]
        recomputed = [
            item
            for item in control_ready_task_ids(root, database)
            if item not in jobs["selected"] and item != blocked
        ]
        return _loop_result(
            jobs,
            root=root,
            now=now,
            results=results,
            next_job=recomputed[0]
            if recomputed
            else (remaining_ready[0] if remaining_ready else None),
            control_recomputed=recomputed,
        )


def _loop_result(
    jobs: dict[str, Any],
    *,
    root: Path,
    now: datetime,
    results: list[dict[str, Any]],
    next_job: str | None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "selected": jobs["selected"],
        "blocked": jobs["blocked"],
        "blocked_reason": jobs["blocked_reason"],
        "skipped_structural": jobs["skipped_structural"],
        "results": results,
        "next_job": next_job,
        "overlay": bound_overlay(root),
        "control_input_root": str(control_input_root(root)),
        "observed_at_utc": now.isoformat(),
        **extra,
    }


def _selected_job_ids(completed: list[dict[str, Any]]) -> list[Any]:
    return [job_id for item in completed for job_id in (item.get("selected") or [])]


def run_available_work(
    *,
    root: Path,
    database: Path,
    ready: list[str],
    blocked: str | None,
    profiles: tuple[MachineProfile, ...],
    adapter: Any,
    workspace: Path,
    workspace_root: Path,
    source_sha: str,
    source_tree: str,
    overlay_sha256: str,
    principal: str,
    now: datetime | None = None,
    deadline: datetime | None = None,
    journal: FleetLifecycleJournal | None = None,
) -> dict[str, Any]:
    """Dispatch every currently ready independent job, then stop. Empty ready fails closed."""

    if not ready:
        return {
            "ok": False,
            "reason": "director_ready_empty",
            "completed_jobs": [],
            "next_job": None,
            "selected": [],
        }
    remaining = [item for item in ready if item != blocked and is_executable_job(item)]
    if not remaining:
        return {
            "ok": False,
            "reason": "no_executable_leaf_ready",
            "completed_jobs": [],
            "next_job": None,
            "selected": [],
            "blocked": blocked,
            "duplicate_work_audit": duplicate_work_audit(root),
        }
    completed: list[dict[str, Any]] = []
    while remaining and (deadline is None or datetime.now(UTC) < deadline):
        result = run_loop(
            root=root,
            database=database,
            ready=remaining,
            blocked=blocked,
            profiles=profiles,
            adapter=adapter,
            workspace=workspace,
            workspace_root=workspace_root,
            source_sha=source_sha,
            source_tree=source_tree,
            overlay_sha256=overlay_sha256,
            principal=principal,
            now=now,
            journal=journal,
        )
        completed.append(result)
        dispatched = [item for item in (result.get("results") or []) if isinstance(item, dict)]
        if not result.get("selected"):
            return {
                "ok": False,
                "reason": str(result.get("reason") or "no_executable_leaf_ready"),
                "completed_jobs": completed,
                "next_job": None,
                "selected": [],
                "blocked": blocked,
            }
        if any(str(item.get("outcome") or "") != "ACCEPTED" for item in dispatched):
            return {
                "ok": False,
                "reason": "selected_work_unresolved",
                "completed_jobs": completed,
                "next_job": remaining[0] if remaining else None,
                "selected": _selected_job_ids(completed),
                "blocked": blocked,
            }
        done = {
            str(item.get("task_id") or "")
            for item in dispatched
            if item.get("outcome") == "ACCEPTED"
        }
        remaining = [item for item in remaining if item not in done and is_executable_job(item)]
    return {
        "ok": True,
        "completed_jobs": completed,
        "next_job": remaining[0] if remaining else None,
        "selected": _selected_job_ids(completed),
        "blocked": blocked,
    }


def _observation_dir(root: Path) -> Path:
    path = root.resolve() / ".local" / "cycle21_observation"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _observation_database(root: Path, database: Path | None, *, live_ssh: bool, out: Path) -> Path:
    if database is not None:
        return Path(database)
    if live_ssh:
        return load_runtime_configuration(root).settings.database_path(root)
    return out / "scheduler.sqlite3"


def _cli_status_from_process(root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    src = str((root / "src").resolve())
    existing = str(env.get("PYTHONPATH") or "")
    env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing
    completed = subprocess.run(
        [sys.executable, "-m", "project_pipeline", "fleet-loop", "status", "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
        cwd=str(root),
        env=env,
    )
    try:
        payload, _ = json.JSONDecoder().raw_decode(completed.stdout.lstrip())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _operator_surfaces(
    *, root: Path, status_path: Path, journal: FleetLifecycleJournal
) -> dict[str, Any]:
    file_status: dict[str, Any] = {}
    if status_path.is_file():
        try:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            file_status = loaded
    cli = _cli_status_from_process(root)
    independent = FleetLifecycleJournal(journal.database)
    occupancy = independent.occupancy_by_host(authority="lease-store")
    events = independent.events()
    journal_events = journal.events()
    fault = cli.get("fault") if isinstance(cli.get("fault"), dict) else {}
    same = [str(item.get("job_id") or "") for item in events] == [
        str(item.get("job_id") or "") for item in journal_events
    ] and len(events) == len(journal_events)
    independent_read = (
        bool(cli)
        and cli.get("remaining_seconds") == file_status.get("remaining_seconds")
        and independent.database.resolve() != status_path.resolve()
    )
    return {
        "cli_remaining_seconds": cli.get("remaining_seconds"),
        "cli_fault_kind": fault.get("kind"),
        "command_center_journal_events": len(events),
        "command_center_occupancy_hosts": sorted(occupancy),
        "same_journal": same,
        "cli_ui_independent": independent_read,
    }


def independent_cli_ui(heartbeats: list[dict[str, Any]]) -> bool:
    return any(bool(item.get("cli_ui_independent")) for item in heartbeats)


def _resource_metrics(
    start_inventories: dict[str, dict[str, Any]],
    end_inventories: dict[str, dict[str, Any]],
    completed_jobs: list[dict[str, Any]],
    *,
    transfer_seconds: float,
) -> dict[str, Any]:
    used: list[float] = []
    for machine_id in (XEON_MACHINE_ID, COMFY_MACHINE_ID):
        start = start_inventories.get(machine_id) or {}
        end = end_inventories.get(machine_id) or start
        total = float(end.get("totalRAMGB") or start.get("totalRAMGB") or 0)
        avail = float(end.get("availableRAMGB") or 0)
        if total > 0:
            used.append(max(0.0, (total - avail) * 1024))
    hosts: set[str] = set()
    for batch in completed_jobs:
        for item in batch.get("results") or []:
            if isinstance(item, dict) and item.get("host_id"):
                hosts.add(str(item["host_id"]))
    scratch = sum(len(json.dumps(item, default=str)) for item in completed_jobs)
    return {
        "peak_ram_mb": max(used) if used else None,
        "scratch_bytes": scratch if scratch else None,
        "transfer_seconds": transfer_seconds if transfer_seconds > 0 else None,
        "concurrency": len(hosts) if hosts else None,
    }


def _xeon_profiles(
    *, when: datetime, inventory: dict[str, Any] | None = None
) -> tuple[MachineProfile, ...]:
    payload = inventory or {
        "hostname": XEON_MACHINE_ID,
        "whoami": r"win-evsh1dn8h5o\kines",
        "totalRAMGB": 63.96,
        "availableRAMGB": 48.0,
        "cpuLogical": 16,
        "cpuPhysical": 8,
        "disks": [{"DeviceID": "C:", "FreeGB": 68.46}],
        "isa": {"sse42": True, "avx": True, "avx2": False},
        "osBuild": "19043",
        "osSupportStatus": "UNSUPPORTED_21H1",
        "measured_at_utc": when.isoformat(),
    }
    observed = apply_inventory_observation(declared_profiles(), payload, when=when)
    return tuple(item for item in observed if item.machine_id == XEON_MACHINE_ID)


def measure_enrolled_inventories() -> dict[str, dict[str, Any]]:
    return {
        XEON_MACHINE_ID: measure_remote_inventory(host=XEON_TAILNET_IPV4, user=XEON_SSH_USER),
        COMFY_MACHINE_ID: measure_remote_inventory(host=COMFY_TAILNET_IPV4, user=COMFY_SSH_USER),
    }


def profiles_from_inventories(
    inventories: dict[str, dict[str, Any]], *, when: datetime
) -> tuple[MachineProfile, ...]:
    profiles = declared_profiles()
    for payload in inventories.values():
        profiles = apply_inventory_observation(profiles, payload, when=when)
    by_id = {item.machine_id: item for item in profiles}
    return (by_id[XEON_MACHINE_ID], by_id[COMFY_MACHINE_ID])


def choose_measured_worker(
    profiles: tuple[MachineProfile, ...],
) -> MachineProfile | None:
    measured = {
        item.machine_id: item
        for item in profiles
        if item.observation_kind == "MEASURED" and item.sid
    }
    return measured.get(XEON_MACHINE_ID) or measured.get(COMFY_MACHINE_ID)


def _measured_hosts(inventories: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        machine_id: measured_host_record(payload, workspace_root=REMOTE_JOB_WORKSPACES[machine_id])
        for machine_id, payload in inventories.items()
    }


def _owned_fault_event(
    envelope: RemoteJobEnvelope, *, status: str, remote_pid: object | None = None
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "job_id": envelope.job_id,
        "host_id": envelope.host_id,
        "lease_id": envelope.lease_id,
        "fence": envelope.fence,
        "status": status,
        "authority": "actor:owned-fault",
    }
    if remote_pid is not None:
        event["remote_pid"] = remote_pid
    return event


def _fault_owned_hold_job(
    *,
    adapter: SshDispatchAdapter,
    store: FleetJobStore,
    journal: FleetLifecycleJournal,
    workspace: Path,
    source_sha: str,
    source_tree: str,
    overlay_sha256: str,
    principal: str,
    now: datetime,
    machine_id: str = XEON_MACHINE_ID,
    scheduler: SchedulerStore | None = None,
) -> dict[str, Any]:
    job_id = "C21-OWNED-FAULT"
    hold = REMOTE_HOLD_SCRIPTS[machine_id]
    lease_id = "C21-OWNED-FAULT-LEASE"
    fence = "owned-fault-1"
    if scheduler is not None:
        bundle = scheduler.acquire_bundle(
            task_id=job_id,
            holder_id="actor:owned-fault",
            claims=(),
            now=now,
        )
        if bundle.acquired and bundle.leases:
            lease_id = bundle.leases[0].lease_id
            fence = str(bundle.leases[0].fencing_token)
    envelope = RemoteJobEnvelope(
        job_id=job_id,
        host_id=machine_id,
        profile_id="MEMORY_HEAVY_BATCH_WORKER",
        principal=principal,
        lease_id=lease_id,
        fence=fence,
        source_sha=source_sha,
        source_tree=source_tree,
        overlay_sha256=overlay_sha256,
        input_sha256=job_input_digest(
            task_id=job_id,
            source_sha=source_sha,
            source_tree=source_tree,
            overlay_sha256=overlay_sha256,
            pack_sha256=overlay_sha256,
            selection=("hold",),
        ),
        argv=("python", hold, "--job-id", job_id, "--seconds", "20", "--output", "hold.json"),
        workspace=str(workspace),
        workspace_root=str(workspace),
        deadline_utc=now + timedelta(minutes=5),
        cpu_ceiling=1,
        memory_mb_ceiling=256,
        correlation_id="actor:owned-fault",
    )
    payload = envelope.model_dump(mode="json")
    stored = store.persist_intent(payload, now=now)
    if not stored.get("ok"):
        return {
            "kind": "owned_durable_fault",
            "recovered": False,
            "owned_job_id": job_id,
            "intent_preserved": store.get_intent(job_id) is not None,
            "reason": stored.get("reason") or "intent_persist_failed",
        }
    journal.publish(_owned_fault_event(envelope, status="DISPATCHED"))
    process = adapter.start_job(
        command=list(envelope.argv),
        working_directory=workspace,
        envelope=payload,
        job_id=job_id,
        input_sha256=envelope.input_sha256,
    )
    started = adapter.read_started_record(process)
    remote_pid = started.get("pid") or started.get("child_pid")
    creation_time = started.get("creation_time") or started.get("child_creation_time")
    journal.publish(_owned_fault_event(envelope, status="RUNNING", remote_pid=remote_pid))
    if not remote_pid or not creation_time:
        store.mark_status(job_id, "UNKNOWN_OUTCOME")
        return {
            "kind": "owned_durable_fault",
            "recovered": False,
            "owned_job_id": job_id,
            "intent_preserved": True,
            "reason": str(started.get("reason") or "pid_not_observed"),
            "lease_id": envelope.lease_id,
            "fence": envelope.fence,
        }
    kill_payload = adapter.kill_pid(
        int(remote_pid),
        workspace=workspace,
        job_id=job_id,
        fence=envelope.fence,
        principal=principal,
        creation_time=str(creation_time),
        envelope=payload,
    )
    killed = bool(kill_payload.get("killed")) and bool(kill_payload.get("ok"))
    store.mark_status(job_id, "UNKNOWN_OUTCOME")
    journal.publish(_owned_fault_event(envelope, status="UNKNOWN_OUTCOME", remote_pid=remote_pid))
    absence_proof = killed
    reconciled = store.reconcile_unresolved(
        job_id, reason="owned_worker_killed", absence_proof=absence_proof
    )
    intent_kept = store.get_intent(job_id) is not None
    recovered_output = False
    recovered_reason: str | None = None
    if killed and reconciled.get("ok"):
        recovered_env = envelope.model_copy(
            update={
                "job_id": f"{job_id}-RECOVERED",
                "fence": f"{fence}-resume",
                "argv": (
                    "python",
                    hold,
                    "--job-id",
                    f"{job_id}-RECOVERED",
                    "--seconds",
                    "1",
                    "--output",
                    "hold.json",
                ),
                "input_sha256": job_input_digest(
                    task_id=f"{job_id}-RECOVERED",
                    source_sha=source_sha,
                    source_tree=source_tree,
                    overlay_sha256=overlay_sha256,
                    pack_sha256=overlay_sha256,
                    selection=("recovered",),
                ),
            }
        )
        store.persist_intent(recovered_env.model_dump(mode="json"), now=now)
        recovered_run = adapter.execute(
            command=list(recovered_env.argv),
            working_directory=workspace,
            envelope=recovered_env.model_dump(mode="json"),
            job_id=recovered_env.job_id,
            input_sha256=recovered_env.input_sha256,
        )
        recovered_output = int(recovered_run.get("exit_code") or 1) == 0
        stdout = str(recovered_run.get("stdout") or "")
        stderr = str(recovered_run.get("stderr") or "")
        output_sha256 = str(
            recovered_run.get("payload_sha256")
            or recovered_run.get("output_sha256")
            or hashlib.sha256(stdout.encode("utf-8")).hexdigest()
        )
        stdout_sha256 = str(
            recovered_run.get("stdout_sha256") or hashlib.sha256(stdout.encode("utf-8")).hexdigest()
        )
        stderr_sha256 = str(
            recovered_run.get("stderr_sha256") or hashlib.sha256(stderr.encode("utf-8")).hexdigest()
        )
        recovered_reason = str(recovered_run.get("reason") or "")
        if recovered_output and len(output_sha256) == 64:
            accepted = store.accept_result(
                {
                    "job_id": recovered_env.job_id,
                    "host_id": recovered_env.host_id,
                    "fence": recovered_env.fence,
                    "exit_code": 0,
                    "output_sha256": output_sha256,
                    "stdout_sha256": stdout_sha256,
                    "stderr_sha256": stderr_sha256,
                },
                now=now,
                envelope=recovered_env.model_dump(mode="json"),
            )
            recovered_output = str(accepted.get("outcome") or "") == "ACCEPTED"
            if not recovered_output:
                recovered_reason = str(
                    accepted.get("reason") or recovered_reason or "accept_rejected"
                )
        else:
            recovered_output = False
    recovered = killed and intent_kept and reconciled.get("ok") is True and recovered_output
    restarted_store = FleetJobStore(store.database)
    controller_restarted = restarted_store.get_intent(job_id) is not None
    return {
        "kind": "owned_durable_fault",
        "recovered": recovered,
        "owned_job_id": job_id,
        "intent_preserved": intent_kept,
        "reconcile_reason": reconciled.get("reason"),
        "killed": killed,
        "remote_pid": remote_pid,
        "creation_time": creation_time,
        "lease_id": envelope.lease_id,
        "fence": envelope.fence,
        "host_id": machine_id,
        "kill_exit_code": kill_payload.get("exit_code"),
        "kill_ok": kill_payload.get("ok"),
        "recovered_output_accepted": recovered_output,
        "recovered_reason": recovered_reason,
        "unaffected_lane_progress": False,
        "controller_restarted": controller_restarted,
        "absence_proof": absence_proof,
    }


def run_observation(
    *,
    root: Path,
    duration_seconds: int,
    database: Path | None = None,
    live_ssh: bool = False,
) -> dict[str, Any]:
    """Bounded mixed useful-work observation. Duration is wall-clock, not a stub."""

    root = root.resolve()
    started = datetime.now(UTC)
    deadline = started + timedelta(seconds=max(1, duration_seconds))
    out = _observation_dir(root)
    identity = inspect_source_identity(root)
    overlay = bound_overlay(root)
    status_path = out / "status.json"
    heartbeats: list[dict[str, Any]] = []
    completed_jobs: list[dict[str, Any]] = []
    principal = r"win-evsh1dn8h5o\kines"
    db = _observation_database(root, database, live_ssh=live_ssh, out=out)
    journal = FleetLifecycleJournal(Path(db).with_name("fleet_lifecycle.sqlite3"))
    live_machine = XEON_MACHINE_ID
    inventories: dict[str, dict[str, Any]] = {}
    if live_ssh:
        inventories = measure_enrolled_inventories()
        profiles = profiles_from_inventories(inventories, when=started)
        chosen = choose_measured_worker(profiles)
        if chosen is None:
            return {
                "ok": False,
                "reason": "no_measured_enrolled_worker",
                "inventories": {
                    machine_id: {
                        "ok": payload.get("ok"),
                        "observation_kind": payload.get("observation_kind"),
                        "reason": payload.get("reason"),
                    }
                    for machine_id, payload in inventories.items()
                },
            }
        live_machine = chosen.machine_id
        adapter = SshDispatchAdapter.for_machine(live_machine)
        workspace = Path(REMOTE_JOB_WORKSPACES[live_machine])
        principal = str(chosen.principal)
    else:
        adapter = LocalSubprocessDispatchAdapter()
        workspace = out / "jobs"
        workspace.mkdir(exist_ok=True)
        profiles = _xeon_profiles(when=started)
    admission_path = Path(db).with_name("fleet_admission.json")
    existing = (
        load_admission_record(admission_path)
        or load_admission_record(root / ".local" / "state" / "fleet_admission.json")
        or {}
    )
    hosts = (
        _measured_hosts(inventories)
        if live_ssh
        else {
            XEON_MACHINE_ID: measured_host_record(
                {},
                workspace_root=REMOTE_JOB_WORKSPACES[XEON_MACHINE_ID],
            )
        }
    )
    write_admission_record(
        admission_path,
        observation_admission_record(
            existing,
            hosts=hosts,
            source_sha=str(identity.get("sha") or existing.get("source_sha") or "a" * 40),
            source_tree=str(identity.get("tree") or existing.get("source_tree") or "b" * 40),
        ),
    )
    pending_owned: list[str] = []
    if live_ssh:
        owned = list(cycle_owned_validation_jobs(profiles))
        ready = owned[:1]
        pending_owned = owned[1:]
        control_ready = observation_ready_task_ids(root, Path(db), live_ssh=True)
        ready.extend(
            item for item in control_ready if item not in ready and item not in pending_owned
        )
        blocked = blocked_dependent_lane(root, Path(db))
    else:
        ready = observation_ready_task_ids(root, Path(db), live_ssh=False)
        blocked = blocked_dependent_lane(root, Path(db))
    dispatch_sha = str(identity.get("sha") or "a" * 40)
    dispatch_tree = str(identity.get("tree") or "b" * 40)
    dispatch_overlay = str(overlay.get("digest") or "c" * 64)
    work: dict[str, Any] = {
        "root": root,
        "database": Path(db),
        "blocked": blocked,
        "profiles": profiles,
        "adapter": adapter,
        "workspace": workspace,
        "workspace_root": out,
        "source_sha": dispatch_sha,
        "source_tree": dispatch_tree,
        "overlay_sha256": dispatch_overlay,
        "principal": principal,
        "deadline": deadline,
        "journal": journal,
    }
    dispatch_started = time.perf_counter()
    available = run_available_work(ready=ready, now=started, **work)
    transfer_seconds = time.perf_counter() - dispatch_started
    completed_jobs = list(available.get("completed_jobs") or [])
    first = (
        completed_jobs[0] if completed_jobs else {"selected": [], "results": [], "next_job": None}
    )
    selected_job = (first.get("selected") or ["none"])[0]
    jobs_store = FleetJobStore(Path(db).with_name("fleet_jobs.sqlite3"))
    sha = str(identity.get("sha") or "").strip().lower()
    tree = str(identity.get("tree") or "").strip().lower()
    overlay_digest = str(overlay.get("digest") or "")
    if (
        live_ssh
        and isinstance(adapter, SshDispatchAdapter)
        and len(sha) == 40
        and len(tree) == 40
        and len(overlay_digest) == 64
    ):
        fault = _fault_owned_hold_job(
            adapter=adapter,
            store=jobs_store,
            journal=journal,
            workspace=workspace,
            source_sha=sha,
            source_tree=tree,
            overlay_sha256=overlay_digest,
            principal=principal,
            now=started,
            machine_id=live_machine,
        )
        other_hosts = {
            str(item.get("host_id") or "")
            for batch in completed_jobs
            for item in (batch.get("results") or [])
            if isinstance(item, dict)
            and item.get("outcome") == "ACCEPTED"
            and str(item.get("host_id") or "") not in {"", live_machine}
        }
        fault["unaffected_lane_progress"] = bool(other_hosts)
        fault["blocked_lane"] = blocked
    else:
        fault = {
            "kind": "owned_durable_fault_not_performed",
            "recovered": False,
            "owned_job_id": None,
            "intent_preserved": False,
            "blocked_lane": blocked,
            "reason": "no_live_owned_running_job",
        }
    next_ready = available.get("next_job")
    selected_ids = set(available.get("selected") or [])
    while datetime.now(UTC) < deadline:
        now = datetime.now(UTC)
        remaining = (deadline - now).total_seconds()
        elapsed = (now - started).total_seconds()
        if live_ssh and pending_owned and elapsed >= 45:
            more = run_available_work(ready=list(pending_owned), now=now, **work)
            completed_jobs.extend(list(more.get("completed_jobs") or []))
            selected_ids.update(more.get("selected") or [])
            next_ready = more.get("next_job")
            pending_owned = []
            other_hosts = {
                str(item.get("host_id") or "")
                for batch in completed_jobs
                for item in (batch.get("results") or [])
                if isinstance(item, dict)
                and item.get("outcome") == "ACCEPTED"
                and str(item.get("host_id") or "") not in {"", live_machine}
            }
            fault["unaffected_lane_progress"] = bool(other_hosts)
            continue
        if live_ssh:
            refreshed = [
                item
                for item in control_ready_task_ids(root, Path(db))
                if item not in selected_ids
                and item != blocked
                and item in CYCLE_OWNED_VALIDATION_JOBS
            ]
            if refreshed:
                more = run_available_work(ready=refreshed, now=now, **work)
                completed_jobs.extend(list(more.get("completed_jobs") or []))
                selected_ids.update(more.get("selected") or [])
                next_ready = more.get("next_job")
                continue
        status_payload = {
            "started_at_utc": started.isoformat(),
            "deadline_at_utc": deadline.isoformat(),
            "remaining_seconds": remaining,
            "completed_jobs": len(completed_jobs),
            "next_job": next_ready,
            "blocked": blocked,
            "fault": fault,
        }
        status_path.write_text(
            json.dumps(status_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        surfaces = _operator_surfaces(root=root, status_path=status_path, journal=journal)
        heartbeats.append(
            {
                "at_utc": now.isoformat(),
                "remaining_seconds": remaining,
                "cli": {
                    "remaining_seconds": surfaces["cli_remaining_seconds"],
                    "fault_kind": surfaces["cli_fault_kind"],
                },
                "command_center": {
                    "journal_events": surfaces["command_center_journal_events"],
                    "occupancy_hosts": surfaces["command_center_occupancy_hosts"],
                },
                "same_journal": surfaces["same_journal"],
                "cli_ui_independent": surfaces["cli_ui_independent"],
            }
        )
        sleep_for = min(30.0, max(1.0, remaining))
        time.sleep(sleep_for)
    ended = datetime.now(UTC)
    wall_seconds = (ended - started).total_seconds()
    duration_met = wall_seconds >= duration_seconds
    end_inventories = measure_enrolled_inventories() if live_ssh else inventories
    surfaces_final = (
        heartbeats[-1] if heartbeats else {"cli_ui_independent": False, "same_journal": False}
    )
    resources = _resource_metrics(
        inventories,
        end_inventories,
        completed_jobs,
        transfer_seconds=transfer_seconds,
    )
    cli_ui_independent = bool(
        surfaces_final.get("cli") or surfaces_final.get("command_center")
    ) and independent_cli_ui(heartbeats)
    eval_payload = {
        "duration_met": duration_met,
        "wall_seconds": wall_seconds,
        "fault": fault,
        "source": identity,
        "overlay": overlay,
        "heartbeats": heartbeats,
        "completed_jobs": completed_jobs,
        "lifecycle_events": journal.events(),
        "resources": resources,
        "cli_ui_independent": cli_ui_independent,
        "same_journal": bool(surfaces_final.get("same_journal")),
    }
    evaluated = evaluate_observation(
        eval_payload,
        expected_source_sha=str(identity.get("sha") or ""),
        expected_source_tree=str(identity.get("tree") or ""),
        expected_overlay_sha256=str(overlay.get("digest") or ""),
        require_useful_work=True,
        require_owned_recovery=True,
        required_seconds=duration_seconds,
    )
    result = {
        "ok": bool(evaluated.get("ok")),
        "evaluation": evaluated,
        "started_at_utc": started.isoformat(),
        "ended_at_utc": ended.isoformat(),
        "wall_seconds": wall_seconds,
        "required_seconds": duration_seconds,
        "duration_met": duration_met,
        "completed_jobs": completed_jobs,
        "blocked_lane": blocked,
        "selected_job": selected_job,
        "next_job": next_ready,
        "fault": fault,
        "heartbeats": heartbeats,
        "ui_heartbeat_tail": heartbeats[-20:],
        "lifecycle_events": journal.events(),
        "source": identity,
        "overlay": overlay,
        "resources": resources,
        "cli_ui_independent": cli_ui_independent,
        "same_journal": bool(surfaces_final.get("same_journal")),
    }
    (out / "USEFUL_WORK_RESULTS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return result


def run_production(*, root: Path, database: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    ready = control_ready_task_ids(root, database)
    blocked = blocked_dependent_lane(root, database)
    identity = inspect_source_identity(root)
    overlay = bound_overlay(root)
    db = database or (root / ".local" / "state" / "scheduler.sqlite3")
    if not ready:
        return {
            "ok": False,
            "reason": "no_executable_leaf_ready",
            "selected": [],
            "blocked": blocked,
            "duplicate_work_audit": duplicate_work_audit(root),
        }
    inventories = measure_enrolled_inventories()
    now = datetime.now(UTC)
    sha = str(identity.get("sha") or "").strip().lower()
    tree = str(identity.get("tree") or "").strip().lower()
    if len(sha) != 40 or len(tree) != 40:
        return {
            "ok": False,
            "reason": "source_identity_missing",
            "selected": [],
            "blocked": blocked,
            "identity": identity,
        }
    overlay_digest = str(overlay.get("digest") or "")
    if overlay.get("ok") is not True or len(overlay_digest) != 64:
        return {
            "ok": False,
            "reason": overlay.get("reason") or "overlay_unbound",
            "selected": [],
            "blocked": blocked,
            "overlay": overlay,
        }
    profiles = profiles_from_inventories(inventories, when=now)
    chosen = choose_measured_worker(profiles)
    if chosen is None:
        return {
            "ok": False,
            "reason": "no_measured_enrolled_worker",
            "selected": [],
            "blocked": blocked,
        }
    adapter = SshDispatchAdapter.for_machine(chosen.machine_id)
    workspace = Path(REMOTE_JOB_WORKSPACES[chosen.machine_id])
    admission_path = Path(db).with_name("fleet_admission.json")
    existing = load_admission_record(admission_path) or {}
    write_admission_record(
        admission_path,
        observation_admission_record(
            existing,
            hosts=_measured_hosts(inventories),
            source_sha=sha,
            source_tree=tree,
        ),
    )
    return run_available_work(
        root=root,
        database=Path(db),
        ready=ready,
        blocked=blocked,
        profiles=profiles,
        adapter=adapter,
        workspace=workspace,
        workspace_root=workspace,
        source_sha=sha,
        source_tree=tree,
        overlay_sha256=overlay_digest,
        principal=str(chosen.principal),
        now=now,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-pipeline fleet-loop")
    parser.add_argument("action", choices=("run", "observe", "status"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--database", type=Path)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--live-ssh", action="store_true")
    parser.add_argument("--json-output", type=Path)
    return parser


def _persist_json_output(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.action == "status":
        status = _observation_dir(args.root) / "status.json"
        payload = (
            json.loads(status.read_text(encoding="utf-8"))
            if status.is_file()
            else {
                "action": "status",
                "running": False,
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        _persist_json_output(args.json_output, payload)
        return 0
    if args.action == "observe":
        result = run_observation(
            root=args.root,
            duration_seconds=args.duration_seconds,
            database=args.database,
            live_ssh=bool(args.live_ssh),
        )
        print(
            json.dumps(
                {k: result[k] for k in result if k != "completed_jobs"},
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        _persist_json_output(args.json_output, result)
        evaluation = result.get("evaluation") if isinstance(result.get("evaluation"), dict) else {}
        return 0 if result.get("ok") and evaluation.get("ok") else 2
    result = run_production(root=args.root, database=args.database)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    _persist_json_output(args.json_output, result)
    return 0 if result.get("selected") else 2


if __name__ == "__main__":
    raise SystemExit(main())
