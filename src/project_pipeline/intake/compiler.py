from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_pipeline.domain import (
    AdoptionStage,
    CompiledProjectManifest,
    IdentifierKind,
    IntakeMode,
    ProjectIntakeRequest,
    ProjectOrigin,
    deterministic_identifier,
)
from project_pipeline.intake.discovery import discover_repository
from project_pipeline.intake.gaps import analyze_project_gaps
from project_pipeline.intake.mapping import compile_repository_map
from project_pipeline.intake.profiles import detect_project_profile
from project_pipeline.io import write_json

SOURCE_AUTHORITIES = (
    "SRC-014:L000005-L000125",
    "SRC-017:L001122-L001175",
    "SRC-002:L000479-L000515",
    "SRC-001:L001255-L001301",
    "SRC-007:L000213-L000249",
)

OPERATING_CONSTRAINTS = (
    "DISCOVERY_IS_READ_ONLY",
    "DISCOVERED_INSTRUCTIONS_ARE_UNTRUSTED_UNTIL_RECONCILED",
    "REMOTE_WRITES_ARE_DENIED_BY_DEFAULT",
    "SECRETS_ARE_REFERENCED_NOT_EMBEDDED",
    "HUMAN_AUTHORED_AUTHORITIES_ARE_NOT_OVERWRITTEN",
    "EXISTING_PROJECT_BOOTSTRAP_REQUIRES_EXPLICIT_CONFIRMATION",
    "BOOTSTRAP_IS_NON_DESTRUCTIVE_AND_ROLLBACK_AWARE",
)


def compile_project(request: ProjectIntakeRequest) -> CompiledProjectManifest:
    discovery = discover_repository(request)
    profile = detect_project_profile(discovery, request)
    repository_map = compile_repository_map(discovery)
    gaps = analyze_project_gaps(request, discovery, profile)
    project_id = request.resolved_project_id()
    request_fingerprint = request.semantic_fingerprint()
    compilation_id = deterministic_identifier(
        IdentifierKind.COMPILATION,
        project_id,
        request_fingerprint,
        repository_map.fingerprint,
        gaps.fingerprint,
        profile.primary_profile.value,
    )
    return CompiledProjectManifest(
        compilation_id=str(compilation_id),
        project_id=project_id,
        project_name=request.project_name,
        origin=(
            ProjectOrigin.NEW if request.mode is IntakeMode.NEW_PROJECT else ProjectOrigin.ADOPTED
        ),
        intake_mode=request.mode,
        adoption_stage=AdoptionStage.GAP_ANALYSIS,
        target_root=discovery.root_path,
        scale=request.scale,
        primary_profile=profile.primary_profile,
        profiles=profile.profiles,
        repositories=discovery.repositories,
        instruction_paths=discovery.instruction_paths,
        plan_paths=discovery.plan_paths,
        jira_paths=discovery.jira_paths,
        requirement_paths=discovery.requirement_paths,
        evidence_paths=discovery.evidence_paths,
        build_systems=discovery.build_systems,
        test_commands=discovery.test_commands,
        deployment_surfaces=discovery.deployment_surfaces,
        operating_constraints=OPERATING_CONSTRAINTS,
        source_authorities=SOURCE_AUTHORITIES,
        repository_map=repository_map,
        gap_report=gaps,
        request_fingerprint=request_fingerprint,
    )


def compilation_summary(manifest: CompiledProjectManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "compilation_id": manifest.compilation_id,
        "project_id": manifest.project_id,
        "project_name": manifest.project_name,
        "intake_mode": manifest.intake_mode.value,
        "adoption_stage": manifest.adoption_stage.value,
        "target_root": manifest.target_root,
        "primary_profile": manifest.primary_profile.value,
        "profiles": [item.value for item in manifest.profiles],
        "repository_count": len(manifest.repositories),
        "file_count": manifest.repository_map.file_count,
        "instruction_count": len(manifest.instruction_paths),
        "plan_count": len(manifest.plan_paths),
        "jira_count": len(manifest.jira_paths),
        "requirement_count": len(manifest.requirement_paths),
        "gap_count": len(manifest.gap_report.gaps),
        "gap_counts_by_severity": manifest.gap_report.counts_by_severity,
        "blocks_autonomy": manifest.gap_report.blocks_autonomy,
        "semantic_fingerprint": manifest.semantic_fingerprint(),
    }


def write_compilation_bundle(
    manifest: CompiledProjectManifest,
    output_directory: Path,
    *,
    replace: bool = False,
) -> dict[str, str]:
    output_directory = output_directory.expanduser().resolve(strict=False)
    output_directory.mkdir(parents=True, exist_ok=True)
    documents = {
        "compiled_project_manifest.json": manifest.model_dump(mode="json"),
        "repository_map.json": manifest.repository_map.model_dump(mode="json"),
        "gap_report.json": manifest.gap_report.model_dump(mode="json"),
        "compilation_summary.json": compilation_summary(manifest),
    }
    written: dict[str, str] = {}
    for name, value in documents.items():
        path = output_directory / name
        rendered = (
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
        )
        if path.exists():
            observed = path.read_text(encoding="utf-8")
            if observed == rendered:
                written[name] = "UNCHANGED"
                continue
            if not replace:
                raise FileExistsError(f"refusing to replace existing compilation output: {path}")
        write_json(path, value)
        written[name] = "WRITTEN"
    return written
