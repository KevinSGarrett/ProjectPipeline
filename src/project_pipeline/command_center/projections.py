from __future__ import annotations

from typing import Any

from project_pipeline.command_center.models import (
    CommandCenterSnapshot,
    HealthDimension,
    HealthState,
    LiveWorkItem,
    ReadinessMetric,
)

_HEALTH_ORDER = {
    HealthState.UNKNOWN: 0,
    HealthState.HEALTHY: 1,
    HealthState.DEGRADED: 2,
    HealthState.UNHEALTHY: 3,
    HealthState.CRITICAL: 4,
}


class CommandCenterProjectionService:
    """Build read-only operator projections from already-authoritative Project Pipeline facts."""

    @staticmethod
    def overall_health(dimensions: tuple[HealthDimension, ...]) -> HealthState:
        if not dimensions:
            return HealthState.UNKNOWN
        if any(item.stale or item.state is HealthState.UNKNOWN for item in dimensions):
            known = [
                item.state
                for item in dimensions
                if not item.stale and item.state is not HealthState.UNKNOWN
            ]
            if not known:
                return HealthState.UNKNOWN
            worst = max(known, key=_HEALTH_ORDER.__getitem__)
            return (
                worst
                if _HEALTH_ORDER[worst] >= _HEALTH_ORDER[HealthState.UNHEALTHY]
                else HealthState.UNKNOWN
            )
        return max((item.state for item in dimensions), key=_HEALTH_ORDER.__getitem__)

    def build_snapshot(
        self,
        *,
        snapshot_id: str,
        project_id: str,
        operating_mode: str,
        health: tuple[HealthDimension, ...],
        completion_gate_state: str = "UNKNOWN",
        completion_percent: float | None = None,
        readiness: tuple[ReadinessMetric, ...] = (),
        live_work: tuple[LiveWorkItem, ...] = (),
        active_incident_ids: tuple[str, ...] = (),
        approval_count: int = 0,
        decision_count: int = 0,
        evidence_count: int = 0,
        budget_summary: dict[str, Any] | None = None,
        provider_summary: dict[str, Any] | None = None,
        context_summary: dict[str, Any] | None = None,
    ) -> CommandCenterSnapshot:
        raw: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "operating_mode": operating_mode,
            "overall_health": self.overall_health(health).value,
            "health": [x.model_dump(mode="json") for x in health],
            "completion_gate_state": completion_gate_state,
            "completion_percent": completion_percent,
            "readiness": [x.model_dump(mode="json") for x in readiness],
            "live_work": [x.model_dump(mode="json") for x in live_work],
            "active_incident_ids": list(active_incident_ids),
            "approval_count": approval_count,
            "decision_count": decision_count,
            "evidence_count": evidence_count,
            "budget_summary": budget_summary or {},
            "provider_summary": provider_summary or {},
            "context_summary": context_summary or {},
            "canonical_authority": "PROJECT_PIPELINE",
            "ui_state_authoritative": False,
        }
        fingerprint = CommandCenterSnapshot.fingerprint_for(raw)
        return CommandCenterSnapshot(**raw, fingerprint=fingerprint)
