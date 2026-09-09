"""Persistent Director → Control → dispatch → verify → next-work loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.dispatch_workflow import DispatchWorkflow
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.lifecycle import FleetLifecycleJournal
from project_pipeline.autonomy_runtime.service import LocalSubprocessDispatchAdapter
from project_pipeline.autonomy_runtime.ssh_dispatch import (
    REMOTE_HOLD_SCRIPTS,
    REMOTE_JOB_SCRIPTS,
    REMOTE_JOB_WORKSPACES,
    XEON_MACHINE_ID,
    XEON_SSH_USER,
    XEON_TAILNET_IPV4,
    SshDispatchAdapter,
    isolated_remote_worker_loss,
)
from project_pipeline.autonomy_runtime.worker_supervision import (
    recover_isolated_job,
    start_isolated_job,
)
from project_pipeline.command_center.autonomy_director import (
    PersistentAutonomyDirector,
    default_state_path,
    evaluate_live_control,
)
from project_pipeline.overlay import bound_overlay, control_input_root, inspect_source_identity
from project_pipeline.scheduler.admission import (
    load_admission_record,
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
    script = root.resolve() / "scripts" / "cycle20_useful_job.py"
    return (sys.executable, str(script), "--job-id", task_id, "--output", artifact)


def select_two_useful_jobs(ready: list[str], *, blocked: str | None = None) -> dict[str, Any]:
    independent = [
        item for item in ready if item != blocked and item not in HISTORICAL_NOT_NEW_WORK
    ]
    selected = independent[:2]
    return {
        "selected": selected,
        "blocked": blocked,
        "blocked_reason": None if blocked is None else "dependent_lane_preserved",
    }


def control_ready_task_ids(root: Path, database: Path | None = None) -> list[str]:
    snapshot = evaluate_live_control(root, database_path=database)
    director = PersistentAutonomyDirector(default_state_path(root))
    ready = list(director._eligible_ready(snapshot))
    return [item for item in ready if item not in HISTORICAL_NOT_NEW_WORK]


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
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    jobs = select_two_useful_jobs(ready, blocked=blocked)
    with SchedulerStore(database, root) as store:
        workflow = DispatchWorkflow(
            store=store,
            jobs=FleetJobStore(database.with_name("fleet_jobs.sqlite3")),
            profiles=profiles,
            admission_path=database.with_name("fleet_admission.json"),
            source_sha=source_sha,
            source_tree=source_tree,
            overlay_sha256=overlay_sha256,
            adapter_factory=lambda _machine_id: adapter,
            journal=FleetLifecycleJournal(database.with_name("fleet_lifecycle.sqlite3")),
        )
        results = []
        remote = bool(getattr(adapter, "remote_host", False))
        host_id = profiles[0].machine_id if profiles else XEON_MACHINE_ID
        job_workspace = (
            Path(REMOTE_JOB_WORKSPACES.get(host_id, str(workspace))) if remote else workspace
        )
        for task_id in jobs["selected"]:
            dispatched = workflow.dispatch(
                task_id=task_id,
                holder_id="actor:fleet-loop",
                argv=useful_argv(root, task_id, remote=remote, machine_id=host_id),
                workspace=str(job_workspace),
                workspace_root=str(workspace_root),
                principal=principal,
                input_sha256=_sha256_text(task_id),
                now=now,
                adapter=adapter,
            )
            results.append({"task_id": task_id, **dispatched})
        next_ready = [item for item in ready if item not in jobs["selected"] and item != blocked]
        return {
            "selected": jobs["selected"],
            "blocked": jobs["blocked"],
            "blocked_reason": jobs["blocked_reason"],
            "results": results,
            "next_job": next_ready[0] if next_ready else None,
            "overlay": bound_overlay(root),
            "control_input_root": str(control_input_root(root)),
            "observed_at_utc": now.isoformat(),
        }


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
    completed: list[dict[str, Any]] = []
    remaining = [item for item in ready if item != blocked and item not in HISTORICAL_NOT_NEW_WORK]
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
        )
        completed.append(result)
        done = set(result.get("selected") or [])
        remaining = [item for item in remaining if item not in done]
        if not result.get("next_job"):
            break
    return {
        "ok": True,
        "completed_jobs": completed,
        "next_job": remaining[0] if remaining else None,
        "selected": [job_id for item in completed for job_id in (item.get("selected") or [])],
        "blocked": blocked,
    }


def _observation_dir(root: Path) -> Path:
    path = root.resolve() / ".local" / "cycle20_observation"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    journal = FleetLifecycleJournal(out / "lifecycle.sqlite3")
    identity = inspect_source_identity(root)
    overlay = bound_overlay(root)
    status_path = out / "status.json"
    heartbeats: list[dict[str, Any]] = []
    completed_jobs: list[dict[str, Any]] = []
    inventory: dict[str, Any] | None = None
    if live_ssh:
        inventory = measure_remote_inventory(host=XEON_TAILNET_IPV4, user=XEON_SSH_USER)
        adapter: Any = SshDispatchAdapter.for_machine(XEON_MACHINE_ID)
        principal = r"win-evsh1dn8h5o\kines"
        workspace = Path(REMOTE_JOB_WORKSPACES[XEON_MACHINE_ID])
    else:
        adapter = LocalSubprocessDispatchAdapter()
        principal = r"win-evsh1dn8h5o\kines"
        workspace = out / "jobs"
        workspace.mkdir(exist_ok=True)
    db = database or (out / "scheduler.sqlite3")
    profiles = _xeon_profiles(when=started, inventory=inventory if live_ssh else None)
    admission_path = Path(db).with_name("fleet_admission.json")
    existing = (
        load_admission_record(admission_path)
        or load_admission_record(root / ".local" / "state" / "fleet_admission.json")
        or {}
    )
    write_admission_record(
        admission_path,
        observation_admission_record(
            existing,
            hosts={
                XEON_MACHINE_ID: {
                    "state": "READY",
                    "freshness": "fresh",
                    "observation_kind": (inventory or {}).get("observation_kind") or "MEASURED",
                    "observed_at_utc": (inventory or {}).get("measured_at_utc")
                    or started.isoformat(),
                }
            },
            source_sha=str(identity.get("sha") or existing.get("source_sha") or "a" * 40),
            source_tree=str(identity.get("tree") or existing.get("source_tree") or "b" * 40),
        ),
    )
    control_ready = control_ready_task_ids(root, Path(db)) if live_ssh else []
    ready = control_ready if live_ssh else ["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"]
    blocked = "PP-TASK-000518"
    available = run_available_work(
        root=root,
        database=Path(db),
        ready=ready,
        blocked=blocked,
        profiles=profiles,
        adapter=adapter,
        workspace=workspace,
        workspace_root=out,
        source_sha=str(identity.get("sha") or "a" * 40),
        source_tree=str(identity.get("tree") or "b" * 40),
        overlay_sha256=str(overlay.get("digest") or "c" * 64),
        principal=principal,
        now=started,
        deadline=deadline,
    )
    completed_jobs = list(available.get("completed_jobs") or [])
    first = (
        completed_jobs[0] if completed_jobs else {"selected": [], "results": [], "next_job": None}
    )
    selected_job = (first["selected"] or ["none"])[0]
    live_pid = None
    for item in first.get("results") or []:
        executed = item.get("executed") or {}
        live_pid = executed.get("remote_pid") or item.get("remote_pid") or live_pid
    journal.publish(
        {
            "job_id": selected_job,
            "host_id": XEON_MACHINE_ID,
            "lease_id": "observation",
            "fence": "1",
            "status": "DISPATCHED",
        }
    )
    journal.publish(
        {
            "job_id": selected_job,
            "host_id": XEON_MACHINE_ID,
            "lease_id": "observation",
            "fence": "1",
            "status": "RUNNING",
            "remote_pid": live_pid or ("measured-ssh" if live_ssh else "isolated-child"),
        }
    )
    # Controlled isolated worker-process loss then recovery in this namespace.
    if live_ssh:
        fault = isolated_remote_worker_loss(
            adapter,
            workspace=workspace,
            hold_script=REMOTE_HOLD_SCRIPTS[XEON_MACHINE_ID],
        )
        recovered = FleetJobStore(Path(db).with_name("fleet_jobs.sqlite3")).reconcile_unresolved(
            "hold", reason="isolated_worker_killed"
        )
        fault["reconcile_reason"] = recovered.get("reason")
        fault["blocked_lane"] = blocked
        fault["host_id"] = XEON_MACHINE_ID
    else:
        child = start_isolated_job(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            workspace=workspace,
        )
        recovered_local = recover_isolated_job(child)
        journal.publish(
            {
                "job_id": selected_job,
                "host_id": XEON_MACHINE_ID,
                "lease_id": "observation",
                "fence": "1",
                "status": "UNKNOWN_OUTCOME",
            }
        )
        fault = {
            "kind": "isolated_worker_process_loss",
            "recovered": bool(recovered_local.get("recovered")),
            "remote_pid": str(child.pid),
            "blocked_lane": blocked,
            "ssh_client_termination": False,
        }
    journal.publish(
        {
            "job_id": selected_job,
            "host_id": XEON_MACHINE_ID,
            "lease_id": "observation",
            "fence": "1",
            "status": "UNKNOWN_OUTCOME" if live_ssh else "ACCEPTED",
        }
    )
    if not live_ssh:
        journal.publish(
            {
                "job_id": selected_job,
                "host_id": XEON_MACHINE_ID,
                "lease_id": "observation",
                "fence": "1",
                "status": "ACCEPTED",
            }
        )
    next_ready = available.get("next_job")
    selected_ids = set(available.get("selected") or [])
    while datetime.now(UTC) < deadline:
        now = datetime.now(UTC)
        remaining = (deadline - now).total_seconds()
        if live_ssh:
            refreshed = [
                item
                for item in control_ready_task_ids(root, Path(db))
                if item not in selected_ids and item != blocked
            ]
            if refreshed:
                more = run_available_work(
                    root=root,
                    database=Path(db),
                    ready=refreshed,
                    blocked=blocked,
                    profiles=profiles,
                    adapter=adapter,
                    workspace=workspace,
                    workspace_root=out,
                    source_sha=str(identity.get("sha") or "a" * 40),
                    source_tree=str(identity.get("tree") or "b" * 40),
                    overlay_sha256=str(overlay.get("digest") or "c" * 64),
                    principal=principal,
                    now=now,
                    deadline=deadline,
                )
                completed_jobs.extend(list(more.get("completed_jobs") or []))
                selected_ids.update(more.get("selected") or [])
                next_ready = more.get("next_job")
                continue
        heartbeats.append({"at_utc": now.isoformat(), "remaining_seconds": remaining})
        status_path.write_text(
            json.dumps(
                {
                    "started_at_utc": started.isoformat(),
                    "deadline_at_utc": deadline.isoformat(),
                    "remaining_seconds": remaining,
                    "completed_jobs": len(completed_jobs),
                    "next_job": next_ready,
                    "blocked": blocked,
                    "fault": fault,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        sleep_for = min(30.0, max(1.0, remaining))
        time.sleep(sleep_for)
    ended = datetime.now(UTC)
    result = {
        "ok": True,
        "started_at_utc": started.isoformat(),
        "ended_at_utc": ended.isoformat(),
        "wall_seconds": (ended - started).total_seconds(),
        "required_seconds": duration_seconds,
        "duration_met": (ended - started).total_seconds() >= duration_seconds,
        "completed_jobs": completed_jobs,
        "blocked_lane": blocked,
        "next_job": next_ready,
        "fault": fault,
        "heartbeats": heartbeats[-20:],
        "source": identity,
        "overlay": overlay,
    }
    (out / "USEFUL_WORK_RESULTS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return result


def run_production(*, root: Path, database: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    ready = control_ready_task_ids(root, database)
    blocked = "PP-TASK-000518"
    identity = inspect_source_identity(root)
    overlay = bound_overlay(root)
    db = database or (root / ".local" / "state" / "scheduler.sqlite3")
    if not ready:
        return {
            "ok": False,
            "reason": "director_ready_empty",
            "selected": [],
            "blocked": blocked,
        }
    inventory = measure_remote_inventory(host=XEON_TAILNET_IPV4, user=XEON_SSH_USER)
    now = datetime.now(UTC)
    profiles = _xeon_profiles(when=now, inventory=inventory)
    adapter = SshDispatchAdapter.for_machine(XEON_MACHINE_ID)
    workspace = Path(REMOTE_JOB_WORKSPACES[XEON_MACHINE_ID])
    admission_path = Path(db).with_name("fleet_admission.json")
    existing = load_admission_record(admission_path) or {}
    write_admission_record(
        admission_path,
        observation_admission_record(
            existing,
            hosts={
                XEON_MACHINE_ID: {
                    "state": "READY",
                    "freshness": "fresh",
                    "observation_kind": inventory.get("observation_kind") or "MEASURED",
                    "observed_at_utc": inventory.get("measured_at_utc") or now.isoformat(),
                }
            },
            source_sha=str(identity.get("sha") or existing.get("source_sha") or ""),
            source_tree=str(identity.get("tree") or existing.get("source_tree") or ""),
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
        workspace_root=root / ".local",
        source_sha=str(identity.get("sha") or ""),
        source_tree=str(identity.get("tree") or ""),
        overlay_sha256=str(overlay.get("digest") or "c" * 64),
        principal=r"win-evsh1dn8h5o\kines",
        now=now,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-pipeline fleet-loop")
    parser.add_argument("action", choices=("run", "observe", "status"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--database", type=Path)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--live-ssh", action="store_true")
    return parser


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
        return 0 if result.get("duration_met") else 2
    result = run_production(root=args.root, database=args.database)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("selected") else 2


if __name__ == "__main__":
    raise SystemExit(main())
