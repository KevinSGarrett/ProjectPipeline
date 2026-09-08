"""In-memory fleet projection with audited drain/resume."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from project_pipeline.scheduler.fleet import MachineProfile, drain_host, fleet_projection, resume_host


class FleetRegistry:
    def __init__(self, profiles: tuple[MachineProfile, ...] = ()) -> None:
        self._profiles = {item.machine_id: item for item in profiles}
        self.audit: list[dict[str, Any]] = []

    def replace(self, profiles: tuple[MachineProfile, ...]) -> None:
        self._profiles = {item.machine_id: item for item in profiles}

    def profiles(self) -> tuple[MachineProfile, ...]:
        return tuple(self._profiles.values())

    def projection(self, *, when: datetime | None = None) -> list[dict[str, Any]]:
        when = (when or datetime.now(UTC)).astimezone(UTC)
        return fleet_projection(self.profiles(), when=when)

    def drain(self, machine_id: str, *, actor: str) -> dict[str, Any]:
        profile = self._profiles.get(machine_id)
        if profile is None:
            return {"ok": False, "reason": "unknown_host"}
        updated = drain_host(profile)
        self._profiles[machine_id] = updated
        record = {
            "action": "drain",
            "machine_id": machine_id,
            "actor": actor,
            "at_utc": datetime.now(UTC).isoformat(),
        }
        self.audit.append(record)
        return {"ok": True, "profile": updated.model_dump(mode="json"), "audit": record}

    def resume(self, machine_id: str, *, actor: str) -> dict[str, Any]:
        profile = self._profiles.get(machine_id)
        if profile is None:
            return {"ok": False, "reason": "unknown_host"}
        updated = resume_host(profile)
        self._profiles[machine_id] = updated
        record = {
            "action": "resume",
            "machine_id": machine_id,
            "actor": actor,
            "at_utc": datetime.now(UTC).isoformat(),
        }
        self.audit.append(record)
        return {"ok": True, "profile": updated.model_dump(mode="json"), "audit": record}
