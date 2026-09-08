"""Bounded remote job envelope and exactly-once result acceptance."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field

from project_pipeline.autonomy_runtime.service import LocalSubprocessDispatchAdapter
from project_pipeline.domain.base import DomainModel

JobOutcome = Literal["ACCEPTED", "REJECTED", "UNKNOWN_OUTCOME"]


class DispatchAdapter(Protocol):
    def execute(
        self,
        *,
        command: list[str],
        working_directory: Path,
        timeout_seconds: int = 60,
        max_output_bytes: int = 65536,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...


class RemoteJobEnvelope(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    job_id: str
    host_id: str
    profile_id: str
    principal: str
    lease_id: str
    fence: str
    source_sha: str = Field(min_length=40, max_length=40)
    source_tree: str = Field(min_length=40, max_length=40)
    overlay_sha256: str
    input_sha256: str
    argv: tuple[str, ...]
    workspace: str
    deadline_utc: datetime
    cpu_ceiling: int = Field(ge=1)
    memory_mb_ceiling: int = Field(ge=1)
    correlation_id: str

    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class RemoteJobResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    job_id: str
    host_id: str
    fence: str
    exit_code: int
    stdout_sha256: str
    stderr_sha256: str
    output_sha256: str
    accepted_at_utc: datetime | None = None


class RemoteJobController:
    def __init__(self, adapter: DispatchAdapter | None = None) -> None:
        self.adapter: DispatchAdapter = adapter or LocalSubprocessDispatchAdapter()
        self._accepted: dict[str, RemoteJobResult] = {}
        self._expired_fences: set[str] = set()

    def expire_fence(self, fence: str) -> None:
        self._expired_fences.add(fence)

    def execute(
        self, envelope: RemoteJobEnvelope, *, now: datetime | None = None
    ) -> dict[str, Any]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        if envelope.fence in self._expired_fences:
            return {"outcome": "REJECTED", "reason": "expired_fence"}
        if now > envelope.deadline_utc:
            return {"outcome": "UNKNOWN_OUTCOME", "reason": "deadline_elapsed"}
        workspace = Path(envelope.workspace)
        remote = bool(getattr(self.adapter, "remote_host", False))
        if not remote and not workspace.is_dir():
            return {"outcome": "REJECTED", "reason": "workspace_missing"}
        payload = self.adapter.execute(
            command=list(envelope.argv),
            working_directory=workspace,
        )
        if payload.get("timed_out"):
            return {"outcome": "UNKNOWN_OUTCOME", "reason": "lost_acknowledgement"}
        result = RemoteJobResult(
            job_id=envelope.job_id,
            host_id=envelope.host_id,
            fence=envelope.fence,
            exit_code=int(payload["exit_code"]),
            stdout_sha256=str(payload["stdout_sha256"]),
            stderr_sha256=str(payload["stderr_sha256"]),
            output_sha256=str(payload["payload_sha256"]),
        )
        return {"outcome": "EXECUTED", "result": result, "envelope_digest": envelope.digest()}

    def accept(
        self,
        envelope: RemoteJobEnvelope,
        result: RemoteJobResult,
        *,
        expected_host: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        if result.job_id != envelope.job_id:
            return {"outcome": "REJECTED", "reason": "wrong_job"}
        if result.host_id != expected_host or result.host_id != envelope.host_id:
            return {"outcome": "REJECTED", "reason": "wrong_host"}
        if envelope.fence in self._expired_fences or result.fence != envelope.fence:
            return {"outcome": "REJECTED", "reason": "expired_fence"}
        existing = self._accepted.get(envelope.job_id)
        if existing is not None:
            if (
                existing.output_sha256 == result.output_sha256
                and existing.exit_code == result.exit_code
            ):
                return {"outcome": "ACCEPTED", "duplicate": True, "result": existing}
            return {"outcome": "REJECTED", "reason": "conflicting_replay"}
        accepted = result.model_copy(update={"accepted_at_utc": now})
        self._accepted[envelope.job_id] = accepted
        return {"outcome": "ACCEPTED", "duplicate": False, "result": accepted}
