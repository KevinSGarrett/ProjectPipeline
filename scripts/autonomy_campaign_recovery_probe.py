"""Campaign-aware scheduled recovery probe. Does not embed secrets or mutate elapsed time."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# Scheduled tasks can inherit an unrelated checkout's PYTHONPATH.  Select the
# candidate checkout before importing any project module, not only after an
# import failure.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
_src_str = str(_SRC_ROOT)
_filtered: list[str] = []
for _entry in sys.path:
    if not _entry:
        _filtered.append(_entry)
        continue
    try:
        _resolved = Path(_entry).resolve()
    except OSError:
        _filtered.append(_entry)
        continue
    if _resolved == _SRC_ROOT or _resolved.name.casefold() == "src":
        continue
    _filtered.append(_entry)
sys.path[:] = _filtered
sys.path.insert(0, _src_str)
_loaded_root = sys.modules.get("project_pipeline")
_loaded_file = getattr(_loaded_root, "__file__", None)
_foreign_project_modules = False
if _loaded_file:
    try:
        _foreign_project_modules = not Path(_loaded_file).resolve().is_relative_to(_SRC_ROOT)
    except OSError:
        _foreign_project_modules = True
if _foreign_project_modules:
    for _name in tuple(
        name
        for name in sys.modules
        if name == "project_pipeline" or name.startswith("project_pipeline.")
    ):
        sys.modules.pop(_name, None)

from project_pipeline.autonomy_runtime.campaign import (  # noqa: E402
    CampaignController,
    evaluate_campaign_aware_health,
)
from project_pipeline.autonomy_runtime.campaign_status import CampaignStatusError  # noqa: E402
from project_pipeline.autonomy_runtime.process_identity import inspect_process  # noqa: E402

TERMINAL_CAMPAIGN_STATUSES = frozenset({"DISQUALIFIED", "FAILED", "STOPPED", "FINALIZED"})


def _load_config(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise SystemExit("recovery config must be a JSON object")
    return payload


def _retarget_config(path: Path, config: dict, campaign: dict) -> None:
    """Atomically bind future recovery probes to the successor campaign."""

    updated = dict(config)
    updated["campaign_id"] = str(campaign["campaign_id"])
    updated["fence"] = str(campaign["fence"])
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _terminal_successor(
    controller: CampaignController,
    campaign: dict,
    *,
    expected_sha: str,
    expected_tree: str,
) -> dict | None:
    """Return the single eligible child left by a failed retarget, if any."""

    rows = controller._db.execute(
        """
        SELECT campaign_id
        FROM campaign_runs
        WHERE prior_campaign_id = ?
          AND integrated_sha = ?
          AND integrated_tree = ?
          AND COALESCE(service_identity, '') = COALESCE(?, '')
          AND status IN ('ATTESTED', 'RUNNING')
        ORDER BY started_at_utc
        """,
        (
            campaign["campaign_id"],
            expected_sha,
            expected_tree,
            campaign.get("service_identity"),
        ),
    ).fetchall()
    if len(rows) != 1:
        return None
    return controller.get(str(rows[0]["campaign_id"]))


def _pid_file_identity(path: Path) -> dict | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    try:
        return {"process_id": int(raw)}
    except ValueError:
        return None


def _qualification_owner_live(controller: CampaignController) -> dict | None:
    try:
        lock = controller._db.execute(
            "SELECT process_id FROM qualification_locks WHERE lock_name = 'active-qualification'"
        ).fetchone()
    except sqlite3.Error:
        return None
    if lock is None:
        return None
    return inspect_process(int(lock["process_id"]))


def _campaign_lock_live(controller: CampaignController) -> dict | None:
    try:
        lock = controller._db.execute(
            "SELECT process_id FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchone()
    except sqlite3.Error:
        return None
    if lock is None:
        return None
    return inspect_process(int(lock["process_id"]))


def _healthy(
    campaign: dict,
    pid_identity: dict | None,
    max_age: float,
    binding: dict | None = None,
    qualification_owner: dict | None = None,
    campaign_lock_owner: dict | None = None,
    expected_sha: str = "",
    expected_tree: str = "",
    expected_fence: str = "",
) -> bool:
    live = campaign_lock_owner
    if live is None and pid_identity and pid_identity.get("process_id"):
        live = inspect_process(int(pid_identity["process_id"]))
    verdict = evaluate_campaign_aware_health(
        campaign=campaign,
        owner_binding=binding,
        pid_identity=pid_identity,
        qualification_owner_live=qualification_owner,
        campaign_lock_live=live,
        expected_sha=expected_sha,
        expected_tree=expected_tree,
        expected_fence=expected_fence,
        heartbeat_max_age_seconds=max_age,
    )
    return bool(verdict["healthy"])


def _parse_campaign_id(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and payload.get("campaign_id"):
        return str(payload["campaign_id"])
    marker = '"campaign_id"'
    index = text.find(marker)
    if index < 0:
        return ""
    fragment = text[index:]
    try:
        start = fragment.find(":")
        quote = fragment.find('"', start)
        end = fragment.find('"', quote + 1)
        return fragment[quote + 1 : end]
    except ValueError:
        return ""


def _run_controller(
    python: str,
    script: Path,
    action: str,
    database: Path,
    root: Path,
    campaign_id: str,
    heartbeat_seconds: float,
    extra: list[str] | None = None,
    *,
    wait: bool,
    stdout_path: Path,
    stderr_path: Path,
) -> subprocess.Popen[str] | subprocess.CompletedProcess[str]:
    args = [
        python,
        str(script),
        action,
        "--database",
        str(database),
        "--campaign-id",
        campaign_id,
        "--repository-root",
        str(root),
        "--heartbeat-seconds",
        str(heartbeat_seconds),
    ]
    if extra:
        args.extend(extra)
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONUTF8": "1"}
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    if wait:
        return subprocess.run(
            args,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    stdout_handle = stdout_path.open("a", encoding="utf-8")
    stderr_handle = stderr_path.open("a", encoding="utf-8")
    return subprocess.Popen(
        args,
        cwd=str(root),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        shell=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed campaign recovery probe")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = _load_config(args.config)
    root = Path(str(config["repository_root"])).resolve()
    database = Path(str(config["database"]))
    python = str(config["python_exe"])
    campaign_id = str(config.get("campaign_id") or "")
    status_path = Path(str(config["status_path"]))
    pid_path = Path(str(config["pid_path"]))
    log_dir = Path(str(config.get("log_directory") or pid_path.parent))
    max_age = float(config.get("heartbeat_max_age_seconds") or 90)
    heartbeat_seconds = float(config.get("heartbeat_seconds") or 30)
    script = root / "scripts" / "run_autonomy_campaign.py"
    controller = CampaignController(
        database,
        repository_root=root,
        heartbeat_seconds=heartbeat_seconds,
    )
    try:
        if not campaign_id:
            running = controller.current_running_campaigns()
            if len(running) > 1:
                raise SystemExit("multiple RUNNING campaigns present")
            if running:
                campaign_id = str(running[0]["campaign_id"])
        if not campaign_id:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                json.dumps(
                    {
                        "healthy": False,
                        "action": "no-campaign",
                        "campaign_module": str(
                            Path(sys.modules[CampaignController.__module__].__file__).resolve()
                        ),
                        "user_action_required": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return 0
        campaign = controller.get(campaign_id)
        expected_sha = str(config.get("expected_sha") or "")
        expected_tree = str(config.get("expected_tree") or "")
        if expected_sha and campaign["integrated_sha"] != expected_sha:
            raise SystemExit("campaign SHA does not match bound expected SHA")
        if expected_tree and campaign["integrated_tree"] != expected_tree:
            raise SystemExit("campaign tree does not match bound expected tree")
        fence = str(config.get("fence") or "")
        if fence and campaign["fence"] != fence:
            raise SystemExit("campaign fence does not match bound fence")
        if str(campaign["status"]) in TERMINAL_CAMPAIGN_STATUSES:
            successor = _terminal_successor(
                controller,
                campaign,
                expected_sha=str(campaign["integrated_sha"]),
                expected_tree=str(campaign["integrated_tree"]),
            )
            if successor is not None:
                try:
                    _retarget_config(args.config, config, successor)
                except OSError:
                    controller.project_status(
                        campaign_id,
                        status_path=status_path,
                        task_health={"registered": True, "probe": "retarget-pending"},
                    )
                    print(
                        json.dumps(
                            {
                                "action": "retarget-pending",
                                "campaign_id": campaign_id,
                                "successor_campaign_id": successor["campaign_id"],
                                "user_action_required": False,
                            },
                            sort_keys=True,
                        )
                    )
                    return 0
                campaign = successor
                campaign_id = str(successor["campaign_id"])
                fence = str(successor["fence"])
            else:
                controller.project_status(
                    campaign_id,
                    status_path=status_path,
                    task_health={"registered": True, "probe": "inactive"},
                )
                print(
                    json.dumps(
                        {
                            "action": "inactive",
                            "campaign_id": campaign_id,
                            "status": campaign["status"],
                            "user_action_required": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
        pid_identity = _pid_file_identity(pid_path)
        if _healthy(
            campaign,
            pid_identity,
            max_age,
            controller._owner_binding(),
            qualification_owner=_qualification_owner_live(controller),
            campaign_lock_owner=_campaign_lock_live(controller),
            expected_sha=expected_sha,
            expected_tree=expected_tree,
            expected_fence=fence,
        ):
            controller.project_status(
                campaign_id,
                status_path=status_path,
                task_health={"registered": True, "probe": "healthy"},
            )
            print(json.dumps({"action": "healthy", "campaign_id": campaign_id}, sort_keys=True))
            return 0
        recovered = _run_controller(
            python,
            script,
            "recover",
            database,
            root,
            campaign_id,
            heartbeat_seconds,
            wait=True,
            stdout_path=log_dir / "campaign.recover.stdout.log",
            stderr_path=log_dir / "campaign.recover.stderr.log",
        )
        assert isinstance(recovered, subprocess.CompletedProcess)
        (log_dir / "campaign.recover.stdout.log").write_text(
            recovered.stdout or "", encoding="utf-8"
        )
        (log_dir / "campaign.recover.stderr.log").write_text(
            recovered.stderr or "", encoding="utf-8"
        )
        if recovered.returncode != 0:
            raise SystemExit(recovered.stderr or "recover failed")
        resume_id = _parse_campaign_id(recovered.stdout or "") or campaign_id
        resumed = controller.get(resume_id)
        if resume_id != campaign_id:
            try:
                _retarget_config(args.config, config, resumed)
            except OSError:
                controller.project_status(
                    campaign_id,
                    status_path=status_path,
                    task_health={"registered": True, "probe": "retarget-pending"},
                )
                print(
                    json.dumps(
                        {
                            "action": "retarget-pending",
                            "campaign_id": campaign_id,
                            "successor_campaign_id": resume_id,
                            "user_action_required": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
        extra: list[str] = []
        if int(config.get("cycles") or 0) > 0:
            extra.extend(["--cycles", str(int(config["cycles"]))])
        creation = _run_controller(
            python,
            script,
            "run",
            database,
            root,
            resume_id,
            heartbeat_seconds,
            extra,
            wait=False,
            stdout_path=log_dir / "campaign.stdout.log",
            stderr_path=log_dir / "campaign.stderr.log",
        )
        assert isinstance(creation, subprocess.Popen)
        pid_path.write_text(
            json.dumps(
                {
                    "process_id": creation.pid,
                    "campaign_id": resume_id,
                    "executable": python,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            lock = controller._db.execute(
                "SELECT process_id FROM campaign_locks WHERE lock_name = 'active-campaign'"
            ).fetchone()
            if lock is not None and int(lock["process_id"]) == int(creation.pid):
                break
            time.sleep(0.2)
        try:
            controller.project_status(
                resume_id,
                status_path=status_path,
                task_health={"registered": True, "probe": "recovered"},
            )
        except (CampaignStatusError, KeyError):
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                json.dumps(
                    {
                        "action": "recovered",
                        "campaign_id": resume_id,
                        "user_action_required": False,
                        "runner_pid": creation.pid,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        print(
            json.dumps(
                {
                    "action": "recovered",
                    "campaign_id": resume_id,
                    "user_action_required": False,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
