from __future__ import annotations

from typing import Any

from project_pipeline.domain import (
    BootstrapOutcome,
    CompiledProjectManifest,
    ProjectIntakeRequest,
)
from project_pipeline.intake import (
    compilation_summary,
    compile_project,
    detect_project_profile,
    discover_repository,
    discovery_summary,
    execute_bootstrap,
)
from project_pipeline.persistence import SQLiteStateStore


class ProjectIntakeService:
    """Read-only discovery and controlled bootstrap over the local persistence port."""

    def __init__(self, store: SQLiteStateStore) -> None:
        self.store = store

    def inspect(self, request: ProjectIntakeRequest) -> dict[str, Any]:
        discovery = discover_repository(request)
        profile = detect_project_profile(discovery, request)
        return {
            "schema_version": "1.0.0",
            "request_fingerprint": request.semantic_fingerprint(),
            "discovery": discovery.model_dump(mode="json"),
            "summary": discovery_summary(discovery),
            "profile_detection": profile.model_dump(mode="json"),
        }

    def compile(
        self, request: ProjectIntakeRequest, *, persist: bool = True
    ) -> tuple[CompiledProjectManifest, dict[str, str | bool] | None]:
        manifest = compile_project(request)
        persistence: dict[str, str | bool] | None = None
        if persist:
            self.store.initialize()
            persistence = self.store.put_intake_compilation(
                manifest,
                actor_id=request.actor_id,
                correlation_id=request.correlation_id,
            )
        return manifest, persistence

    def bootstrap(
        self,
        manifest: CompiledProjectManifest,
        *,
        apply: bool,
        confirm_existing: bool,
        actor_id: str,
        correlation_id: str,
        persist: bool = True,
    ) -> dict[str, Any]:
        plan, receipt = execute_bootstrap(
            manifest,
            apply=apply,
            confirm_existing=confirm_existing,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        persistence: dict[str, str | bool] | None = None
        if persist:
            self.store.initialize()
            self.store.put_intake_compilation(
                manifest,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            persistence = self.store.put_bootstrap_receipt(receipt)
        return {
            "schema_version": "1.0.0",
            "plan": plan.model_dump(mode="json"),
            "receipt": receipt.model_dump(mode="json"),
            "persistence": persistence,
            "ok": receipt.outcome
            in {BootstrapOutcome.DRY_RUN, BootstrapOutcome.APPLIED, BootstrapOutcome.NO_CHANGES},
        }

    def status(
        self,
        *,
        compilation_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        self.store.initialize()
        if compilation_id is not None:
            manifest = self.store.get_intake_compilation(compilation_id)
            if manifest is None:
                return {
                    "schema_version": "1.0.0",
                    "found": False,
                    "compilation_id": compilation_id,
                }
            receipts = self.store.list_bootstrap_receipts(compilation_id)
            return {
                "schema_version": "1.0.0",
                "found": True,
                "compilation": manifest.model_dump(mode="json"),
                "summary": compilation_summary(manifest),
                "bootstrap_receipts": [item.model_dump(mode="json") for item in receipts],
            }
        manifests = self.store.list_intake_compilations(project_id)
        return {
            "schema_version": "1.0.0",
            "found": bool(manifests),
            "project_id": project_id,
            "compilation_count": len(manifests),
            "compilations": [compilation_summary(item) for item in manifests],
        }
