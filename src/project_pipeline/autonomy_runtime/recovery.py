from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from project_pipeline.autonomy_runtime.lanes import LaneRegistry


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RecoveryIncident:
    lane_id: str
    reason: str
    state: str
    created_at_utc: datetime


def recover_lane_loss(
    *,
    registry: LaneRegistry,
    lane_id: str,
    stale_fencing_token: str,
) -> RecoveryIncident:
    released = registry.release(lane_id=lane_id, fencing_token=stale_fencing_token)
    if released:
        return RecoveryIncident(
            lane_id=lane_id,
            reason="LEASE_RELEASED",
            state="RECOVERED",
            created_at_utc=_utc_now(),
        )
    return RecoveryIncident(
        lane_id=lane_id,
        reason="UNRESOLVED_STALE_OR_UNKNOWN_LEASE",
        state="HUMAN_REQUIRED",
        created_at_utc=_utc_now(),
    )
