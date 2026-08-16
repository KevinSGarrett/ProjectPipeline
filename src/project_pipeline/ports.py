from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ActionContext:
    actor_id: str
    correlation_id: str
    idempotency_key: str
    authority_scope: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    decision_id: str
    policy_version: str
    reasons: tuple[str, ...] = ()
    required_approvals: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowHandle:
    workflow_id: str
    state: str


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    capability: str
    payload: Mapping[str, Any]
    maximum_cost_microunits: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider_id: str
    output: Mapping[str, Any]
    usage: Mapping[str, int]
    evidence_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolRequest:
    tool_id: str
    operation: str
    arguments: Mapping[str, Any]
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class ToolResult:
    outcome: str
    output: Mapping[str, Any]
    external_operation_id: str | None = None
    evidence_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    algorithm: str
    digest: str
    size_bytes: int
    media_type: str


@runtime_checkable
class WorkflowRuntime(Protocol):
    def start(
        self, workflow_name: str, payload: Mapping[str, Any], context: ActionContext
    ) -> WorkflowHandle: ...
    def status(self, workflow_id: str) -> WorkflowHandle: ...
    def cancel(self, workflow_id: str, context: ActionContext) -> WorkflowHandle: ...


@runtime_checkable
class PolicyPort(Protocol):
    def evaluate(
        self, action: str, resource: Mapping[str, Any], context: ActionContext
    ) -> PolicyDecision: ...


@runtime_checkable
class ProviderPort(Protocol):
    def invoke(self, request: ProviderRequest, context: ActionContext) -> ProviderResult: ...


@runtime_checkable
class ToolPort(Protocol):
    def invoke(self, request: ToolRequest, context: ActionContext) -> ToolResult: ...


@runtime_checkable
class ArtifactStore(Protocol):
    def put(
        self, content: bytes, media_type: str = "application/octet-stream"
    ) -> ArtifactReference: ...
    def get(self, reference: ArtifactReference) -> bytes: ...
    def verify(self, reference: ArtifactReference) -> bool: ...


@runtime_checkable
class TelemetryPort(Protocol):
    def emit(
        self, signal: str, attributes: Mapping[str, str], measurements: Mapping[str, float]
    ) -> None: ...


@runtime_checkable
class CapabilityRegistry(Protocol):
    def candidates(self, capability: str) -> Sequence[str]: ...


@runtime_checkable
class RepositoryPort(Protocol):
    def head_revision(self, repository_id: str) -> str: ...
    def changed_paths(
        self, repository_id: str, base_revision: str, head_revision: str
    ) -> Sequence[str]: ...


@runtime_checkable
class WorkTrackerPort(Protocol):
    def read_item(self, external_id: str) -> Mapping[str, Any]: ...
    def reconcile(
        self, external_id: str, intended_state: Mapping[str, Any], context: ActionContext
    ) -> Mapping[str, Any]: ...


@runtime_checkable
class ObjectByteStorePort(Protocol):
    def put_if_absent(self, key: str, content: bytes, media_type: str) -> str: ...
    def read(self, key: str) -> bytes: ...
    def verify(self, key: str, expected_digest: str) -> bool: ...
