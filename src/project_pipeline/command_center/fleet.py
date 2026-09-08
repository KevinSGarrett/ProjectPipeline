"""In-memory fleet projection with audited drain/resume."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.scheduler.fleet import (
    MachineProfile,
    drain_host,
    fleet_projection,
    resume_host,
)


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
        if profile.state == "ENROLLMENT_PENDING":
            return {
                "ok": False,
                "reason": "drain_denied:ENROLLMENT_PENDING",
                "profile": profile.model_dump(mode="json"),
            }
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
        if profile.state in {"ENROLLMENT_PENDING", "QUARANTINED", "OFFLINE"}:
            return {
                "ok": False,
                "reason": f"resume_denied:{profile.state}",
                "profile": profile.model_dump(mode="json"),
            }
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

    def persist(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0.0",
            "hosts": [item.model_dump(mode="json") for item in self.profiles()],
            "audit": list(self.audit),
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load_or_declared(cls, path: Path, declared: tuple[MachineProfile, ...]) -> FleetRegistry:
        if not path.is_file():
            return cls(declared)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(declared)
        hosts = payload.get("hosts") if isinstance(payload, dict) else None
        if not isinstance(hosts, list) or not hosts:
            return cls(declared)
        registry = cls(tuple(MachineProfile.model_validate(item) for item in hosts))
        registry.audit = list(payload.get("audit") or [])
        return registry
