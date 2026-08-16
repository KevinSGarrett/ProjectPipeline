from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from project_pipeline.domain import (
    BootstrapReceipt,
    CompiledProjectManifest,
    DomainStateTransition,
    ProjectManifest,
    ProjectStateRecord,
    RequirementRecord,
    TaskStateRecord,
    TraceabilityLink,
    TraceabilityMutation,
    TraceabilityMutationResult,
)


class CoreStateRepository(Protocol):
    def initialize(self) -> None: ...

    def put_project_manifest(self, manifest: ProjectManifest) -> None: ...

    def get_project_manifest(self, project_id: str) -> ProjectManifest | None: ...

    def get_project_state(self, project_id: str) -> ProjectStateRecord | None: ...

    def get_task_state(self, task_id: str) -> TaskStateRecord | None: ...

    def put_task_states(self, tasks: Iterable[TaskStateRecord]) -> int: ...

    def list_transitions(
        self, *, entity_type: str, entity_id: str
    ) -> tuple[DomainStateTransition, ...]: ...


class RequirementPersistence(Protocol):
    def import_requirements(
        self, requirements: Iterable[RequirementRecord], *, source_path: str, catalog_sha256: str
    ) -> dict[str, int | str]: ...

    def get_requirement(self, requirement_id: str) -> RequirementRecord | None: ...

    def list_requirement_links(self, requirement_id: str) -> tuple[TraceabilityLink, ...]: ...

    def apply_traceability_mutation(
        self, mutation: TraceabilityMutation
    ) -> TraceabilityMutationResult: ...


class ProjectIntakePersistence(Protocol):
    def put_intake_compilation(
        self, manifest: CompiledProjectManifest, *, actor_id: str, correlation_id: str
    ) -> dict[str, int | str | bool]: ...

    def get_intake_compilation(self, compilation_id: str) -> CompiledProjectManifest | None: ...

    def list_intake_compilations(
        self, project_id: str | None = None
    ) -> tuple[CompiledProjectManifest, ...]: ...

    def put_bootstrap_receipt(self, receipt: BootstrapReceipt) -> dict[str, str | bool]: ...

    def list_bootstrap_receipts(self, compilation_id: str) -> tuple[BootstrapReceipt, ...]: ...
