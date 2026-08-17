from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.autonomy_runtime.lanes import Clock, LaneIncident, LaneRegistry


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RecoveryIncident:
    lane_id: str
    reason: str
    state: str
    created_at_utc: datetime
    incident_id: str | None = None
    attempt_id: str | None = None
    failure_fingerprint: str | None = None
    retry_decision: str | None = None


def _from_lane_incident(incident: LaneIncident) -> RecoveryIncident:
    return RecoveryIncident(
        lane_id=incident.logical_lane_id,
        reason=incident.reason,
        state=incident.disposition,
        created_at_utc=incident.created_at_utc,
        incident_id=incident.incident_id,
        attempt_id=incident.attempt_id,
        failure_fingerprint=incident.failure_fingerprint,
        retry_decision=incident.retry_decision,
    )


class DurableRecoveryService:
    """Restart-safe recovery facade over persisted lane incidents and attempts."""

    def __init__(self, registry: LaneRegistry) -> None:
        self.registry = registry

    @classmethod
    def open(
        cls,
        db_path: Path,
        *,
        clock: Clock | None = None,
        max_attempts: int = 3,
    ) -> DurableRecoveryService:
        return cls(LaneRegistry(db_path, clock=clock, max_attempts=max_attempts))

    def close(self) -> None:
        self.registry.close()

    def recover_lost_worker(
        self,
        *,
        lane_id: str,
        stale_fencing_token: str,
        stale_worker_id: str | None = None,
    ) -> RecoveryIncident:
        return _from_lane_incident(
            self.registry.recover_lost_worker(
                lane_id=lane_id,
                stale_fencing_token=stale_fencing_token,
                stale_worker_id=stale_worker_id,
            )
        )

    def incidents(self, lane_id: str | None = None) -> list[RecoveryIncident]:
        return [_from_lane_incident(item) for item in self.registry.list_incidents(lane_id)]


def recover_lane_loss(
    *,
    registry: LaneRegistry,
    lane_id: str,
    stale_fencing_token: str,
    stale_worker_id: str | None = None,
) -> RecoveryIncident:
    return DurableRecoveryService(registry).recover_lost_worker(
        lane_id=lane_id,
        stale_fencing_token=stale_fencing_token,
        stale_worker_id=stale_worker_id,
    )
