"""Bounded productive-idle selection while a distinct lane waits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.domain.control import ControlSnapshot, ReadinessState
from project_pipeline.domain.scheduler import (
    ResourceClaim,
    ResourceType,
    SchedulerPlan,
    SchedulerTaskProfile,
)

_WAITING_STATES = {
    ReadinessState.WAITING_DEPENDENCIES,
    ReadinessState.BLOCKED,
    ReadinessState.WAITING_APPROVAL,
    ReadinessState.WAITING_CONTEXT,
    ReadinessState.WAITING_RESOURCES,
    ReadinessState.WAITING_ENVIRONMENT,
}


def waiting_lane_ids(control: ControlSnapshot) -> tuple[str, ...]:
    return tuple(
        item.task_id
        for item in control.readiness
        if item.state in _WAITING_STATES or (item.state is ReadinessState.ACTIVE and not item.ready)
    )


def _path_keys(claims: tuple[ResourceClaim, ...]) -> set[str]:
    return {claim.resource_key for claim in claims if claim.resource_type is ResourceType.PATH}


def shares_implementation_scope(
    waiting_claims: tuple[ResourceClaim, ...], candidate_claims: tuple[ResourceClaim, ...]
) -> bool:
    waiting_paths = _path_keys(waiting_claims)
    candidate_paths = _path_keys(candidate_claims)
    for left in waiting_paths:
        for right in candidate_paths:
            if left == right or left.startswith(right + "/") or right.startswith(left + "/"):
                return True
    return False


@dataclass(frozen=True, slots=True)
class ProductiveIdleDecision:
    waiting_task_ids: tuple[str, ...]
    selected_task_id: str | None
    progressed: bool
    progress_count: int
    reasons: tuple[str, ...]
    receipt_path: str | None


def evaluate_productive_idle(
    control: ControlSnapshot,
    plan: SchedulerPlan,
    profiles: tuple[SchedulerTaskProfile, ...],
    *,
    waiting_claims: dict[str, tuple[ResourceClaim, ...]] | None = None,
) -> ProductiveIdleDecision:
    """Admit unrelated ready work only while another lane waits.

    Progress is not inferred from a label or the ready list. A selected idle
    lane must already be admitted, must not consume protected capacity, and
    must not share PATH scope with a waiting lane.
    """

    waiting = waiting_lane_ids(control)
    if not waiting:
        return ProductiveIdleDecision((), None, False, 0, ("no_waiting_lane",), None)
    admitted = {lane.task_id for lane in plan.lanes}
    by_id = {item.task_id: item for item in profiles}
    claims = waiting_claims or {}
    waiting_claim_union = tuple(claim for task_id in waiting for claim in claims.get(task_id, ()))
    candidates: list[SchedulerTaskProfile] = []
    reasons: list[str] = [f"waiting:{','.join(waiting)}"]
    for task_id in sorted(admitted):
        profile = by_id.get(task_id)
        if profile is None:
            reasons.append(f"missing_profile:{task_id}")
            continue
        if task_id in waiting:
            reasons.append(f"selected_lane_is_waiting:{task_id}")
            continue
        if profile.protected_capacity_consumption:
            reasons.append(f"protected_capacity:{task_id}")
            continue
        if shares_implementation_scope(waiting_claim_union, profile.claims):
            reasons.append(f"shared_scope:{task_id}")
            continue
        candidates.append(profile)
    if not candidates:
        return ProductiveIdleDecision(waiting, None, False, 0, tuple(reasons), None)
    selected = sorted(candidates, key=lambda item: (item.sequence_rank, item.task_id))[0]
    return ProductiveIdleDecision(
        waiting,
        selected.task_id,
        False,
        0,
        tuple([*reasons, f"selected:{selected.task_id}"]),
        None,
    )


def apply_productive_idle_progress(
    decision: ProductiveIdleDecision,
    store_dir: Path,
    *,
    now: datetime | None = None,
) -> ProductiveIdleDecision:
    """Persist a real progress increment for the selected unrelated lane."""

    if decision.selected_task_id is None:
        return decision
    now = now or datetime.now(UTC)
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / f"{decision.selected_task_id}.json"
    previous: dict[str, Any] = {}
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
    count = int(previous.get("progress_count") or 0) + 1
    payload = {
        "schema_version": "1.0.0",
        "task_id": decision.selected_task_id,
        "waiting_task_ids": list(decision.waiting_task_ids),
        "progress_count": count,
        "previous_progress_count": int(previous.get("progress_count") or 0),
        "updated_at_utc": now.isoformat(),
        "reasons": list(decision.reasons),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ProductiveIdleDecision(
        decision.waiting_task_ids,
        decision.selected_task_id,
        True,
        count,
        decision.reasons,
        str(path),
    )
