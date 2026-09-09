"""Evaluator for the Cycle 20 mixed observation. Elapsed time alone is not PASS."""

from __future__ import annotations

from typing import Any

EXECUTABLE_USEFUL_PREFIX = "PP-TASK-"
SMOKE_USEFUL_PREFIX = "PP-STORY-"


def evaluate_observation(
    payload: dict[str, Any],
    *,
    expected_source_sha: str,
    require_useful_work: bool = True,
    require_owned_recovery: bool = True,
) -> dict[str, Any]:
    reasons: list[str] = []
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    actual_sha = str(source.get("sha") or "")
    if actual_sha.lower() != expected_source_sha.lower():
        reasons.append(f"source_mismatch:{actual_sha}")
    heartbeats = payload.get("heartbeats") if isinstance(payload.get("heartbeats"), list) else []
    if len(heartbeats) < 60:
        reasons.append(f"heartbeat_coverage:{len(heartbeats)}")
    fault = payload.get("fault") if isinstance(payload.get("fault"), dict) else {}
    if require_owned_recovery:
        if fault.get("recovered") is not True:
            reasons.append("recovery_not_proven")
        if str(fault.get("reconcile_reason") or "") == "no_intent":
            reasons.append("recovery_no_intent")
        if not fault.get("owned_job_id"):
            reasons.append("recovery_unowned")
        if not fault.get("intent_preserved"):
            reasons.append("intent_not_preserved")
        if fault.get("killed") and not fault.get("intent_preserved"):
            reasons.append("kill_without_durable_intent")
    jobs = payload.get("completed_jobs") if isinstance(payload.get("completed_jobs"), list) else []
    if require_useful_work:
        smoke = False
        accepted = False
        for batch in jobs:
            for item in (batch.get("results") if isinstance(batch, dict) else []) or []:
                task_id = str(item.get("task_id") or "")
                if task_id.startswith(SMOKE_USEFUL_PREFIX):
                    smoke = True
                if (
                    task_id.startswith(EXECUTABLE_USEFUL_PREFIX)
                    and str(item.get("outcome") or "") == "ACCEPTED"
                ):
                    accepted = True
        if smoke or not accepted:
            reasons.append("useful_work_missing")
    if payload.get("duration_met") and not reasons:
        return {"ok": True, "reasons": []}
    if payload.get("duration_met") and reasons:
        reasons.append("elapsed_time_not_sufficient")
    return {"ok": False, "reasons": reasons}
