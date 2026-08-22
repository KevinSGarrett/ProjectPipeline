from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from project_pipeline.domain.verification import MutationProbeResult, verification_identifier
from project_pipeline.validation.repository import RepositoryValidator


def _copy_repository(root: Path, target: Path) -> None:
    shutil.copytree(
        root,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            "venv",
            ".local",
            ".codex",
            ".codex-*",
            ".codex_*",
            ".codex_backups",
            ".claude",
            ".cursor",
            "Github_Repo",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        ),
    )


def run_mutation_probes(root: Path) -> tuple[MutationProbeResult, ...]:
    baseline = RepositoryValidator(root).validate()
    if not baseline.ok:
        raise ValueError("mutation probes require a clean repository-validation baseline")
    results: list[MutationProbeResult] = []
    mutations: tuple[tuple[str, Callable[[Path], object], str], ...] = (
        (
            "missing-required-assurance-policy",
            lambda copy: (copy / "config" / "assurance_policy.json").unlink(),
            "repository-validator",
        ),
        (
            "stale-generated-schema",
            lambda copy: (
                copy / "schemas" / "assurance_completion_gate_decision.schema.json"
            ).write_text("{}\n", encoding="utf-8"),
            "generated-schema-validator",
        ),
        (
            "forbidden-permanent-token",
            lambda copy: (copy / "MUTATION_PROBE.md").write_text(
                "This mutation intentionally inserts the forbidden cadence token: "
                + "".join(("wa", "ves"))
                + "\n",
                encoding="utf-8",
            ),
            "forbidden-terminology-validator",
        ),
    )
    for name, mutate, detector in mutations:
        with tempfile.TemporaryDirectory(prefix="project-pipeline-mutation-") as temp:
            copy = Path(temp) / root.name
            _copy_repository(root, copy)
            mutate(copy)
            report = RepositoryValidator(copy).validate()
            detected = not report.ok
            results.append(
                MutationProbeResult(
                    mutation_id=verification_identifier("MUTATE", name, detector, str(detected)),
                    mutation_name=name,
                    detector=detector,
                    detected=detected,
                )
            )
    return tuple(results)
