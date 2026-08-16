from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from project_pipeline.assurance import build_repository_gate_facts, evaluate_completion_gate
from project_pipeline.io import iter_repository_files, sha256_file
from project_pipeline.release_hardening.hardening import build_hardening_report
from project_pipeline.release_hardening.models import ReleaseCandidateSnapshot

EXCLUDED_PREFIXES = ("evidence/", "release/generated/")
EXCLUDED_PATHS = {
    "PROJECT_MANIFEST.json",
    "FILE_MANIFEST.sha256",
    "docs/generated/REPOSITORY_MAP.json",
    "docs/generated/REPOSITORY_MAP.md",
    "release/release_candidate_r24.json",
    "release/hardening_report_r24.json",
    "release/sbom_r24.json",
}


def release_input_fingerprint(root: Path) -> str:
    aggregate = hashlib.sha256()
    for path in iter_repository_files(root, excluded_relative_paths=EXCLUDED_PATHS):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        aggregate.update(rel.encode())
        aggregate.update(b"\0")
        aggregate.update(sha256_file(path).encode())
        aggregate.update(b"\n")
    return aggregate.hexdigest()


def build_release_candidate(root: Path) -> ReleaseCandidateSnapshot:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    json.loads((root / "requirements/environment.lock.json").read_text(encoding="utf-8"))
    dep_policy = json.loads((root / "config/dependency_policy.json").read_text(encoding="utf-8"))
    migrations = json.loads((root / "database/MIGRATION_CATALOG.json").read_text(encoding="utf-8"))[
        "migrations"
    ]
    gate = evaluate_completion_gate(build_repository_gate_facts(root, "PROJECT-PIPELINE"))
    hardening = build_hardening_report(root)
    blockers = list(hardening.production_blockers)
    if gate.state.value != "COMPLETE":
        blockers.append(f"Completion Gate state is {gate.state.value}")
    return ReleaseCandidateSnapshot(
        project_version=str(project["version"]),
        candidate_label="r24-local-hardening-candidate",
        input_fingerprint_sha256=release_input_fingerprint(root),
        dependency_environment_fingerprint=sha256_file(root / "requirements/environment.lock.json"),
        resolver_lock_state=str(dep_policy.get("resolver_lock", {}).get("state", "UNKNOWN")),
        migration_ids=tuple(item["migration_id"] for item in migrations),
        configuration_paths=tuple(
            sorted(path.relative_to(root).as_posix() for path in (root / "config").rglob("*.json"))
        ),
        packaging_target_states={
            item.target: item.state.value for item in hardening.packaging_targets
        },
        completion_gate_state=gate.state.value,
        blockers=tuple(dict.fromkeys(blockers)),
    )
