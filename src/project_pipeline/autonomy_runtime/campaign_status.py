"""Atomic current-status projection for autonomy campaigns."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class CampaignStatusError(ValueError):
    """Raised when a status projection is contradictory or stale."""


def _walk_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(_walk_strings(key))
            found.extend(_walk_strings(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_walk_strings(item))
    return found


def validate_status_projection(payload: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    encoded = json.dumps(payload, sort_keys=True, default=str)
    if CONTROL_CHAR_RE.search(encoded) or any(
        CONTROL_CHAR_RE.search(item) for item in _walk_strings(payload)
    ):
        findings.append("status contains ASCII control characters")
    sha = str(payload.get("integrated_sha") or "")
    tree = str(payload.get("integrated_tree") or "")
    if not GIT_SHA_RE.fullmatch(sha):
        findings.append("integrated_sha is abbreviated or nonresolving")
    if not GIT_SHA_RE.fullmatch(tree):
        findings.append("integrated_tree is abbreviated or nonresolving")
    raw_runner = payload.get("runner_owner")
    runner: dict[str, Any] = raw_runner if isinstance(raw_runner, dict) else {}
    claimed_pid = runner.get("process_id")
    if payload.get("heartbeat_fresh") is True and not runner.get("alive"):
        findings.append("stale heartbeat claimed while runner owner is not alive")
    if payload.get("status") == "RUNNING" and runner.get("alive") is False:
        findings.append("RUNNING status with dead runner owner")
    lock_pid = payload.get("lock_process_id")
    if (
        claimed_pid is not None
        and lock_pid is not None
        and int(claimed_pid) != int(lock_pid)
        and payload.get("status") == "RUNNING"
    ):
        findings.append("mismatched lock PID and runner owner PID")
    for row in payload.get("pull_requests") or []:
        if isinstance(row, dict) and bool(row.get("open")) and bool(row.get("merged")):
            findings.append(f"contradictory PR state: {row.get('number')}")
    if payload.get("user_action_required") is not False:
        findings.append("user_action_required must be false")
    return findings


def write_status_projection(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    findings = validate_status_projection(payload)
    if findings:
        raise CampaignStatusError("; ".join(findings))
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
        raise
    return payload


def build_status_projection(
    *,
    campaign: dict[str, Any],
    runner_owner: dict[str, Any] | None,
    lock: dict[str, Any] | None,
    task_health: dict[str, Any] | None = None,
    heartbeat_max_age_seconds: float = 90.0,
    is_final_release_candidate: bool = False,
    pull_requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    last = campaign.get("last_heartbeat_utc")
    last_dt = datetime.fromisoformat(str(last)) if last else None
    if last_dt is not None and last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=UTC)
    age = (now - last_dt).total_seconds() if last_dt else None
    fresh = age is not None and age <= float(heartbeat_max_age_seconds)
    owner = runner_owner or {}
    return {
        "schema_version": "1.0.0",
        "generated_at_utc": now.isoformat(),
        "campaign_id": campaign.get("campaign_id"),
        "qualification_run_id": campaign.get("qualification_run_id"),
        "integrated_sha": campaign.get("integrated_sha"),
        "integrated_tree": campaign.get("integrated_tree"),
        "release_identity": campaign.get("release_identity"),
        "stage": campaign.get("stage"),
        "status": campaign.get("status"),
        "next_transition": campaign.get("next_transition"),
        "fence": campaign.get("fence"),
        "lease_id": campaign.get("lease_id"),
        "window_broken": bool(campaign.get("window_broken")),
        "window_integrity": "broken" if campaign.get("window_broken") else "intact",
        "last_heartbeat_utc": campaign.get("last_heartbeat_utc"),
        "heartbeat_age_seconds": age,
        "heartbeat_fresh": fresh,
        "runner_owner": owner,
        "lock_process_id": None if lock is None else lock.get("process_id"),
        "task_health": task_health or {"registered": False},
        "user_action_required": False,
        "is_final_release_candidate": bool(is_final_release_candidate),
        "simulated_elapsed": False,
        "pull_requests": list(pull_requests or ()),
    }
