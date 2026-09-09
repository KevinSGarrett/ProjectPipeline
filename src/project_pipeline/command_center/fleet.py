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
    merge_occupancy,
    occupancy_from_jobs,
    resume_host,
)


class FleetRegistry:
    def __init__(
        self,
        profiles: tuple[MachineProfile, ...] = (),
        persist_path: Path | None = None,
    ) -> None:
        self._profiles = {item.machine_id: item for item in profiles}
        self.audit: list[dict[str, Any]] = []
        self.jobs: list[dict[str, Any]] = []
        self.persist_path = persist_path

    def replace(self, profiles: tuple[MachineProfile, ...]) -> None:
        self._profiles = {item.machine_id: item for item in profiles}

    def profiles(self) -> tuple[MachineProfile, ...]:
        return tuple(self._profiles.values())

    def projection(
        self,
        *,
        when: datetime | None = None,
        occupancy: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        when = (when or datetime.now(UTC)).astimezone(UTC)
        job_occupancy = occupancy_from_jobs(self.jobs, when=when)
        if occupancy is None and not job_occupancy:
            return fleet_projection(self.profiles(), when=when)
        return fleet_projection(
            self.profiles(),
            when=when,
            occupancy=merge_occupancy(job_occupancy, occupancy or {}),
        )

    def refresh_from_disk(self) -> None:
        if self.persist_path is None or not self.persist_path.is_file():
            return
        loaded = type(self).load_or_declared(self.persist_path, self.profiles())
        self._profiles = {item.machine_id: item for item in loaded.profiles()}
        self.audit = list(loaded.audit)
        self.jobs = list(loaded.jobs)

    def _merge_disk_jobs(self) -> None:
        if self.persist_path is None or not self.persist_path.is_file():
            return
        try:
            payload = json.loads(self.persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        disk_jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(disk_jobs, list):
            return
        merged = {
            str(item.get("job_id")): item
            for item in disk_jobs
            if isinstance(item, dict) and item.get("job_id")
        }
        for item in self.jobs:
            job_id = item.get("job_id")
            if job_id:
                merged[str(job_id)] = item
        self.jobs = list(merged.values())

    def record_job(self, job: dict[str, Any]) -> dict[str, Any]:
        memory_jobs = list(self.jobs)
        if self.persist_path is not None:
            self.refresh_from_disk()
        record = dict(job)
        merged = {
            str(item.get("job_id")): item
            for item in [*memory_jobs, *self.jobs]
            if isinstance(item, dict) and item.get("job_id")
        }
        merged[str(record.get("job_id"))] = record
        self.jobs = list(merged.values())
        self._commit()
        return record

    def _commit(self) -> None:
        if self.persist_path is not None:
            self.persist(self.persist_path)

    def _record_action(self, action: str, machine_id: str, actor: str) -> dict[str, Any]:
        record = {
            "action": action,
            "machine_id": machine_id,
            "actor": actor,
            "at_utc": datetime.now(UTC).isoformat(),
        }
        self.audit.append(record)
        self._commit()
        return record

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
        return {
            "ok": True,
            "profile": updated.model_dump(mode="json"),
            "audit": self._record_action("drain", machine_id, actor),
        }

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
        return {
            "ok": True,
            "profile": updated.model_dump(mode="json"),
            "audit": self._record_action("resume", machine_id, actor),
        }

    def persist(self, path: Path) -> None:
        self.persist_path = path
        self._merge_disk_jobs()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0.0",
            "hosts": [item.model_dump(mode="json") for item in self.profiles()],
            "audit": list(self.audit),
            "jobs": list(self.jobs),
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load_or_declared(cls, path: Path, declared: tuple[MachineProfile, ...]) -> FleetRegistry:
        payload: Any = None
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
        if not isinstance(payload, dict):
            return cls(declared, persist_path=path)
        hosts = payload.get("hosts")
        if not isinstance(hosts, list) or not hosts:
            return cls(declared, persist_path=path)
        registry = cls(
            tuple(MachineProfile.model_validate(item) for item in hosts), persist_path=path
        )
        registry.audit = list(payload.get("audit") or [])
        jobs = payload.get("jobs")
        registry.jobs = (
            [item for item in jobs if isinstance(item, dict)] if isinstance(jobs, list) else []
        )
        return registry
