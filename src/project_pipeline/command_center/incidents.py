from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.models import (
    InboxItem,
    IncidentCase,
    IncidentState,
    NotificationLevel,
)
from project_pipeline.domain.resilience import HumanRequiredIncident
from project_pipeline.resilience.failover import verify_human_repair


class IncidentManager:
    """Operator-facing lifecycle around canonical resilience incidents."""

    def __init__(
        self,
        inbox: AttentionNotificationBroker,
        *,
        case_sink: Callable[[IncidentCase], None] | None = None,
    ) -> None:
        self.inbox = inbox
        self.case_sink = case_sink
        self._cases: dict[str, IncidentCase] = {}

    def open(
        self,
        incident: HumanRequiredIncident,
        *,
        project_id: str,
        severity: NotificationLevel = NotificationLevel.URGENT,
        evidence_ids: tuple[str, ...] = (),
    ) -> IncidentCase:
        existing = self._cases.get(incident.incident_id)
        if existing is not None and existing.state is not IncidentState.RESOLVED:
            return existing
        inbox_item = self.inbox.submit(
            InboxItem(
                inbox_id=f"inbox:{uuid4()}",
                project_id=project_id,
                dedupe_key=f"incident:{incident.incident_id}",
                kind="incident",
                level=severity,
                title=incident.summary,
                impact=self._impact(incident),
                exact_action=f"Autonomous recheck: {incident.exact_human_action}",
                post_action_verification="; ".join(incident.verification_steps),
                critical_path=bool(incident.blocked_work),
                blocked_tasks=len(incident.blocked_work),
                correlation_id=incident.incident_id,
                evidence_ids=evidence_ids,
            )
        )
        case = IncidentCase(
            incident=incident,
            project_id=project_id,
            state=IncidentState.OPEN,
            severity=severity,
            inbox_id=inbox_item.inbox_id,
            evidence_ids=evidence_ids,
        )
        self._save(case)
        return case

    def get(self, incident_id: str) -> IncidentCase:
        return self._cases[incident_id]

    def list_active(self) -> tuple[IncidentCase, ...]:
        rows = [item for item in self._cases.values() if item.state is not IncidentState.RESOLVED]
        return tuple(
            sorted(rows, key=lambda item: (item.incident.created_at_utc, item.incident.incident_id))
        )

    def acknowledge(self, incident_id: str, *, now: datetime | None = None) -> IncidentCase:
        case = self.get(incident_id)
        timestamp = now or datetime.now(UTC)
        if case.inbox_id is not None:
            self.inbox.acknowledge(case.inbox_id, now=timestamp)
        updated = case.model_copy(
            update={"state": IncidentState.ACKNOWLEDGED, "acknowledged_at_utc": timestamp}
        )
        return self._save(updated)

    def begin_recovery(self, incident_id: str, *, now: datetime | None = None) -> IncidentCase:
        case = self.get(incident_id)
        if case.state is IncidentState.RESOLVED:
            raise ValueError("resolved incident cannot re-enter recovery")
        timestamp = now or datetime.now(UTC)
        updated = case.model_copy(
            update={"state": IncidentState.RECOVERING, "recovery_started_at_utc": timestamp}
        )
        return self._save(updated)

    def verify(
        self,
        incident_id: str,
        *,
        verification_results: dict[str, bool],
        stale_assumptions_invalidated: bool,
        reconciliation_complete: bool,
        now: datetime | None = None,
    ) -> IncidentCase:
        case = self.get(incident_id)
        verification = verify_human_repair(
            verification_results=verification_results,
            stale_assumptions_invalidated=stale_assumptions_invalidated,
            reconciliation_complete=reconciliation_complete,
        )
        timestamp = now or datetime.now(UTC)
        state = IncidentState.VERIFIED if verification["verified"] else IncidentState.RECOVERING
        updated = case.model_copy(
            update={
                "state": state,
                "verification": verification,
                "verified_at_utc": timestamp if verification["verified"] else None,
            }
        )
        return self._save(updated)

    def resolve(self, incident_id: str, *, now: datetime | None = None) -> IncidentCase:
        case = self.get(incident_id)
        if case.state is not IncidentState.VERIFIED or not case.verification.get("verified"):
            raise ValueError("incident cannot resolve until repair verification succeeds")
        timestamp = now or datetime.now(UTC)
        if case.inbox_id is not None:
            self.inbox.resolve(case.inbox_id, now=timestamp)
        updated = case.model_copy(
            update={"state": IncidentState.RESOLVED, "resolved_at_utc": timestamp}
        )
        return self._save(updated)

    def _save(self, case: IncidentCase) -> IncidentCase:
        self._cases[case.incident.incident_id] = case
        if self.case_sink is not None:
            self.case_sink(case)
        return case

    @staticmethod
    def _impact(incident: HumanRequiredIncident) -> str:
        blocked = (
            ", ".join(incident.blocked_work)
            if incident.blocked_work
            else "No explicitly blocked work"
        )
        unaffected = (
            ", ".join(incident.unaffected_work)
            if incident.unaffected_work
            else "No unaffected-work list supplied"
        )
        return f"Blocked work: {blocked}. Unaffected work: {unaffected}."
