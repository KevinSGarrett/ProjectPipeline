"""Bounded remote job envelope and restart-safe exactly-once result acceptance."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field

from project_pipeline.autonomy_runtime.confinement import (
    ConfinementError,
    argv_is_confined,
    canonicalize_workspace,
    reject_unsafe_string,
)
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.providers import contains_secret_shaped
from project_pipeline.autonomy_runtime.service import LocalSubprocessDispatchAdapter
from project_pipeline.autonomy_runtime.windows_limits import (
    ResourceLimitError,
    close_job_handle,
    enforce_or_reject,
)
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
        job_handle: int | None = None,
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
    workspace_root: str | None = None
    output_contract_sha256: str | None = None
    effect_class: Literal["IDEMPOTENT_RESULT", "NON_IDEMPOTENT_EFFECT"] = "IDEMPOTENT_RESULT"

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
    def __init__(
        self,
        adapter: DispatchAdapter | None = None,
        store: FleetJobStore | None = None,
        *,
        require_intent: bool = False,
        expected_source_sha: str | None = None,
        expected_source_tree: str | None = None,
        expected_overlay_sha256: str | None = None,
        expected_principal: str | None = None,
        workspace_root: str | None = None,
    ) -> None:
        self.adapter: DispatchAdapter = adapter or LocalSubprocessDispatchAdapter()
        self.store = store
        self.require_intent = require_intent
        self.expected_source_sha = expected_source_sha
        self.expected_source_tree = expected_source_tree
        self.expected_overlay_sha256 = expected_overlay_sha256
        self.expected_principal = expected_principal
        self.workspace_root = workspace_root
        self._accepted: dict[str, RemoteJobResult] = {}
        self._expired_fences: set[str] = set()

    def expire_fence(self, fence: str) -> None:
        self._expired_fences.add(fence)
        if self.store is not None:
            self.store.expire_fence(fence)

    def _fence_expired(self, fence: str) -> bool:
        if fence in self._expired_fences:
            return True
        return bool(self.store and self.store.fence_expired(fence))

    def _authority_failures(self, envelope: RemoteJobEnvelope) -> tuple[str, ...]:
        failures: list[str] = []
        if self.expected_source_sha and envelope.source_sha != self.expected_source_sha:
            failures.append("source_mismatch")
        if self.expected_source_tree and envelope.source_tree != self.expected_source_tree:
            failures.append("tree_mismatch")
        if self.expected_overlay_sha256 and envelope.overlay_sha256 != self.expected_overlay_sha256:
            failures.append("overlay_mismatch")
        if self.expected_principal and envelope.principal != self.expected_principal:
            failures.append("principal_mismatch")
        if self.require_intent:
            if self.store is None:
                failures.append("intent_store_missing")
            else:
                intent = self.store.get_intent(envelope.job_id)
                if intent is None:
                    failures.append("intent_missing")
                elif str(intent.get("lease_id")) != envelope.lease_id:
                    failures.append("lease_mismatch")
                elif str(intent.get("fence")) != envelope.fence:
                    failures.append("fence_mismatch")
        if not argv_is_confined(envelope.argv):
            failures.append("argv_not_confined")
        if contains_secret_shaped(envelope.argv) or contains_secret_shaped(envelope.workspace):
            failures.append("secret_in_argv")
        return tuple(failures)

    def execute(
        self, envelope: RemoteJobEnvelope, *, now: datetime | None = None
    ) -> dict[str, Any]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        if envelope.fence in self._expired_fences or self._fence_expired(envelope.fence):
            return {"outcome": "REJECTED", "reason": "expired_fence"}
        if now > envelope.deadline_utc:
            return {"outcome": "UNKNOWN_OUTCOME", "reason": "deadline_elapsed"}
        authority = self._authority_failures(envelope)
        if authority:
            return {"outcome": "REJECTED", "reason": authority[0], "failures": authority}
        if self.store is not None:
            existing_result = self.store.get_result(envelope.job_id)
            if existing_result is not None:
                return {"outcome": "REJECTED", "reason": "already_accepted"}
            intent = self.store.get_intent(envelope.job_id)
            if intent and str(intent.get("status")) in {"RUNNING", "DISPATCHED"}:
                return {"outcome": "UNKNOWN_OUTCOME", "reason": "unresolved_in_flight"}
            if intent and str(intent.get("status")) == "ACCEPTED":
                return {"outcome": "REJECTED", "reason": "already_accepted"}
        remote = bool(getattr(self.adapter, "remote_host", False))
        adapter_host = getattr(self.adapter, "machine_id", None)
        if remote and envelope.host_id != adapter_host:
            return {"outcome": "REJECTED", "reason": "wrong_host"}
        root = envelope.workspace_root or self.workspace_root
        if remote:
            try:
                reject_unsafe_string(envelope.workspace, field="workspace")
            except ConfinementError as error:
                return {"outcome": "REJECTED", "reason": str(error)}
            workspace = Path(envelope.workspace)
        elif root:
            try:
                workspace = canonicalize_workspace(
                    envelope.workspace, root=root, host_id=envelope.host_id
                )
            except ConfinementError as error:
                return {"outcome": "REJECTED", "reason": str(error)}
        else:
            workspace = Path(envelope.workspace)
        if not remote and not workspace.is_dir():
            return {"outcome": "REJECTED", "reason": "workspace_missing"}
        remaining = max(1, int((envelope.deadline_utc - now).total_seconds()))
        try:
            limits = enforce_or_reject(
                cpu_ceiling=envelope.cpu_ceiling,
                memory_mb_ceiling=envelope.memory_mb_ceiling,
                deadline_seconds=remaining,
            )
        except ResourceLimitError as error:
            return {"outcome": "REJECTED", "reason": str(error)}
        if self.store is not None:
            self.store.mark_status(envelope.job_id, "DISPATCHED")
        try:
            payload = self.adapter.execute(
                command=list(envelope.argv),
                working_directory=workspace,
                timeout_seconds=remaining,
                extra_env=limits.get("env"),
                job_handle=limits.get("handle"),
            )
        except TypeError:
            payload = self.adapter.execute(
                command=list(envelope.argv),
                working_directory=workspace,
                timeout_seconds=remaining,
                extra_env=limits.get("env"),
            )
        finally:
            handle = limits.get("handle")
            close_job_handle(handle if isinstance(handle, int) else None)
        if payload.get("timed_out"):
            if self.store is not None:
                self.store.mark_status(envelope.job_id, "UNKNOWN_OUTCOME")
            return {"outcome": "UNKNOWN_OUTCOME", "reason": "lost_acknowledgement"}
        if self.store is not None:
            self.store.mark_status(envelope.job_id, "RUNNING")
        result = RemoteJobResult(
            job_id=envelope.job_id,
            host_id=str(adapter_host or envelope.host_id),
            fence=envelope.fence,
            exit_code=int(payload["exit_code"]),
            stdout_sha256=str(payload["stdout_sha256"]),
            stderr_sha256=str(payload["stderr_sha256"]),
            output_sha256=str(payload["payload_sha256"]),
        )
        return {
            "outcome": "EXECUTED",
            "result": result,
            "envelope_digest": envelope.digest(),
            "remote_pid": payload.get("remote_pid") or payload.get("pid"),
        }

    def accept(
        self,
        envelope: RemoteJobEnvelope,
        result: RemoteJobResult,
        *,
        expected_host: str,
        now: datetime | None = None,
        artifact_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        if result.job_id != envelope.job_id:
            return {"outcome": "REJECTED", "reason": "wrong_job"}
        if result.host_id != expected_host or result.host_id != envelope.host_id:
            return {"outcome": "REJECTED", "reason": "wrong_host"}
        if self._fence_expired(envelope.fence) or result.fence != envelope.fence:
            return {"outcome": "REJECTED", "reason": "expired_fence"}
        if now > envelope.deadline_utc:
            return {"outcome": "REJECTED", "reason": "late_result"}
        if int(result.exit_code) != 0:
            return {"outcome": "REJECTED", "reason": "nonzero_exit"}
        if envelope.output_contract_sha256:
            actual = result.output_sha256
            if artifact_bytes is not None:
                actual = hashlib.sha256(artifact_bytes).hexdigest()
            if actual != envelope.output_contract_sha256:
                return {"outcome": "REJECTED", "reason": "output_tamper"}
        if self.store is not None:
            stored = self.store.accept_result(result.model_dump(mode="json"), now=now)
            return stored
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
