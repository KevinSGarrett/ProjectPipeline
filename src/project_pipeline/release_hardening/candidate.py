from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

from project_pipeline.assurance import build_repository_gate_facts, evaluate_completion_gate
from project_pipeline.assurance.evidence import load_evidence
from project_pipeline.io import iter_repository_files, sha256_canonical_file, sha256_file
from project_pipeline.release_hardening.hardening import build_hardening_report
from project_pipeline.release_hardening.models import ReleaseCandidateSnapshot

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

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


def resolve_candidate_identity(root: Path) -> tuple[str, str]:
    """Return the exact current HEAD SHA and tree. Fail closed on abbreviated identity."""

    def _rev_parse(argument: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", argument],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
        value = (completed.stdout or "").strip().lower()
        if completed.returncode != 0 or not _FULL_SHA.fullmatch(value):
            raise ValueError(f"release candidate SHA/tree could not be resolved ({argument})")
        return value

    return _rev_parse("HEAD"), _rev_parse("HEAD^{tree}")


def _bound_evidence_ids(root: Path, source_sha: str, source_tree: str) -> tuple[str, ...]:
    bound: list[str] = []
    for row in load_evidence(root):
        evidence_id = str(row.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        sha = str(row.get("integrated_sha") or row.get("head_sha") or "").strip().lower()
        tree = str(row.get("integrated_tree") or row.get("tree_sha") or "").strip().lower()
        if sha == source_sha and tree == source_tree:
            bound.append(evidence_id)
    return tuple(bound)


def build_release_candidate(root: Path) -> ReleaseCandidateSnapshot:
    root = root.resolve()
    source_sha, source_tree = resolve_candidate_identity(root)
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
    project_manifest = root / "PROJECT_MANIFEST.json"
    file_manifest = root / "FILE_MANIFEST.sha256"
    if not project_manifest.is_file() or not file_manifest.is_file():
        raise ValueError(
            "release candidate requires PROJECT_MANIFEST.json and FILE_MANIFEST.sha256"
        )
    return ReleaseCandidateSnapshot(
        project_version=str(project["version"]),
        candidate_label="r24-local-hardening-candidate",
        source_sha=source_sha,
        source_tree=source_tree,
        input_fingerprint_sha256=release_input_fingerprint(root),
        dependency_environment_fingerprint=sha256_file(root / "requirements/environment.lock.json"),
        project_manifest_sha256=sha256_canonical_file(project_manifest),
        file_manifest_sha256=sha256_canonical_file(file_manifest),
        resolver_lock_state=str(dep_policy.get("resolver_lock", {}).get("state", "UNKNOWN")),
        migration_ids=tuple(item["migration_id"] for item in migrations),
        configuration_paths=tuple(
            sorted(path.relative_to(root).as_posix() for path in (root / "config").rglob("*.json"))
        ),
        packaging_target_states={
            item.target: item.state.value for item in hardening.packaging_targets
        },
        evidence_ids=_bound_evidence_ids(root, source_sha, source_tree),
        completion_gate_state=gate.state.value,
        blockers=tuple(dict.fromkeys(blockers)),
    )
