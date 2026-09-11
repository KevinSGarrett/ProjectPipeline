"""Evaluator for mixed fleet observation. Elapsed time alone is not PASS."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.context_validation import junit_case_counts

EXECUTABLE_USEFUL_PREFIX = "PP-TASK-"
SMOKE_USEFUL_PREFIX = "PP-STORY-"
XEON_MACHINE_ID = "WIN-EVSH1DN8H5O"
COMFY_MACHINE_ID = "COMFY-V4-CPU-01"
_ARTIFACT_SHA = re.compile(r"^[a-f0-9]{64}$")


def _parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _heartbeat_coverage(heartbeats: list[Any], *, wall_seconds: float) -> list[str]:
    reasons: list[str] = []
    if len(heartbeats) < 60:
        reasons.append(f"heartbeat_coverage:{len(heartbeats)}")
    stamps: list[str] = []
    parsed: list[datetime] = []
    for item in heartbeats:
        if not isinstance(item, dict):
            reasons.append("heartbeat_unstructured")
            continue
        stamp = str(item.get("at_utc") or "")
        stamps.append(stamp)
        parsed_at = _parse_utc(stamp)
        if parsed_at is None:
            reasons.append("heartbeat_timestamp_invalid")
        else:
            parsed.append(parsed_at)
    if stamps and len(set(stamps)) != len(stamps):
        reasons.append("heartbeat_duplicate_timestamps")
    if parsed:
        span = (max(parsed) - min(parsed)).total_seconds()
        if wall_seconds >= 60 and span < max(30.0, wall_seconds * 0.8):
            reasons.append("heartbeat_span_insufficient")
    return reasons


def _accepted_jobs(jobs: list[Any]) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    for batch in jobs:
        if not isinstance(batch, dict):
            continue
        for item in batch.get("results") or []:
            if not isinstance(item, dict):
                continue
            accepted.append(item)
    return accepted


def _verified_acquired_artifact(item: dict[str, Any]) -> str | None:
    digest = str(item.get("artifact_sha256") or item.get("junit_sha256") or "")
    path = Path(str(item.get("acquired_junit_path") or ""))
    if not _ARTIFACT_SHA.fullmatch(digest) or not path.is_file():
        return None
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        return None
    collected, failed, skipped = junit_case_counts(path)
    if collected < 1 or failed or skipped:
        return None
    item["tests_run"] = collected
    item["collected"] = collected
    return digest


def evaluate_observation(
    payload: dict[str, Any],
    *,
    expected_source_sha: str,
    expected_source_tree: str = "",
    expected_overlay_sha256: str = "",
    require_useful_work: bool = True,
    require_owned_recovery: bool = True,
    required_seconds: int = 3600,
) -> dict[str, Any]:
    reasons: list[str] = []
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    actual_sha = str(source.get("sha") or "")
    actual_tree = str(source.get("tree") or "")
    overlay = payload.get("overlay") if isinstance(payload.get("overlay"), dict) else {}
    actual_overlay = str(overlay.get("digest") or payload.get("overlay_sha256") or "")
    if actual_sha.lower() != expected_source_sha.lower():
        reasons.append(f"source_mismatch:{actual_sha}")
    if expected_source_tree and actual_tree.lower() != expected_source_tree.lower():
        reasons.append(f"tree_mismatch:{actual_tree}")
    if expected_overlay_sha256 and actual_overlay.lower() != expected_overlay_sha256.lower():
        reasons.append("overlay_mismatch")
    wall_seconds = float(payload.get("wall_seconds") or 0)
    if wall_seconds <= 0:
        reasons.append("zero_wall_seconds")
    if wall_seconds + 1 < float(required_seconds):
        reasons.append("duration_not_met")
    if payload.get("duration_met") is True and wall_seconds <= 0:
        reasons.append("duration_claim_without_wall_time")
    heartbeats = payload.get("heartbeats") if isinstance(payload.get("heartbeats"), list) else []
    reasons.extend(_heartbeat_coverage(heartbeats, wall_seconds=wall_seconds))
    fault = payload.get("fault") if isinstance(payload.get("fault"), dict) else {}
    if require_owned_recovery:
        if fault.get("recovered") is not True:
            reasons.append("recovery_not_proven")
        if fault.get("killed") is not True:
            reasons.append("owned_kill_not_proven")
        if str(fault.get("reconcile_reason") or "") in {"absence_proof_required", "no_intent"}:
            reasons.append("recovery_unreconciled")
        if not fault.get("owned_job_id"):
            reasons.append("recovery_unowned")
        if not fault.get("intent_preserved"):
            reasons.append("intent_not_preserved")
        if not fault.get("recovered_output_accepted"):
            reasons.append("recovered_output_missing")
        if not fault.get("unaffected_lane_progress"):
            reasons.append("unaffected_lane_missing")
        if not fault.get("controller_restarted"):
            reasons.append("controller_restart_missing")
        if not (fault.get("remote_pid") or fault.get("controller_pid") or fault.get("pid")):
            reasons.append("recovery_pid_missing")
        if not (fault.get("creation_time") or fault.get("filetime")):
            reasons.append("recovery_filetime_missing")
        if fault.get("controller_restarted") is True and not fault.get("restart_pid"):
            reasons.append("controller_restart_not_a_process")
    jobs = payload.get("completed_jobs") if isinstance(payload.get("completed_jobs"), list) else []
    window_start = _parse_utc(payload.get("started_at_utc"))
    if require_useful_work:
        smoke = False
        accepted_real: list[dict[str, Any]] = []
        hosts: set[str] = set()
        for item in _accepted_jobs(jobs):
            task_id = str(item.get("task_id") or "")
            if task_id.startswith(SMOKE_USEFUL_PREFIX):
                smoke = True
            if item.get("duplicate") is True:
                continue
            artifact = _verified_acquired_artifact(item)
            tests_run = int(item.get("tests_run") or 0)
            executed = item.get("executed") if isinstance(item.get("executed"), dict) else {}
            receipt = (
                item.get("context_consumption")
                or item.get("context_receipt")
                or executed.get("context_consumption")
                or executed.get("context_receipt")
                or {}
            )
            started = _parse_utc(
                item.get("started_at_utc")
                or executed.get("started_at_utc")
                or item.get("accepted_at_utc")
            )
            if window_start and started and started < window_start:
                reasons.append(f"pre_window_job:{task_id}")
                continue
            if not isinstance(receipt, dict) or not receipt.get("ok"):
                reasons.append(f"context_receipt_missing:{task_id}")
                continue
            if (
                str(receipt.get("job_id") or "") not in {"", task_id}
                and str(receipt.get("job_id")) != task_id
            ):
                reasons.append(f"context_wrong_job:{task_id}")
                continue
            if (
                task_id.startswith(EXECUTABLE_USEFUL_PREFIX)
                and str(item.get("outcome") or "") == "ACCEPTED"
                and tests_run > 0
                and artifact
            ):
                accepted_real.append(item)
                host = str(item.get("host_id") or "")
                if host:
                    hosts.add(host)
        if smoke or len(accepted_real) < 2:
            reasons.append("useful_work_missing")
        if XEON_MACHINE_ID not in hosts:
            reasons.append("xeon_assignment_missing")
        if COMFY_MACHINE_ID not in hosts:
            reasons.append("comfy_assignment_missing")
    resources = payload.get("resources") if isinstance(payload.get("resources"), dict) else {}
    for key in ("peak_ram_mb", "scratch_bytes", "transfer_seconds", "concurrency"):
        if resources.get(key) in (None, "", 0, "0"):
            reasons.append(f"resource_metric_missing:{key}")
    if payload.get("same_journal") is True and not payload.get("cli_ui_independent"):
        reasons.append("cli_ui_not_independent")
    if reasons:
        if payload.get("duration_met"):
            reasons.append("elapsed_time_not_sufficient")
        return {"ok": False, "reasons": reasons}
    return {"ok": True, "reasons": []}
