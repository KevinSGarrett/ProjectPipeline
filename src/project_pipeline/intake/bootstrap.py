from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from project_pipeline.domain import (
    BootstrapAction,
    BootstrapActionKind,
    BootstrapOutcome,
    BootstrapPlan,
    BootstrapReceipt,
    CompiledProjectManifest,
    IdentifierKind,
    IntakeMode,
    ProjectProfile,
    deterministic_identifier,
)


class BootstrapError(RuntimeError):
    """Raised when controlled bootstrap cannot preserve its safety contract."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _package_name(project_name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", project_name.lower()).strip("_")
    return value or "project"


def _portable_manifest_content(manifest: CompiledProjectManifest) -> str:
    payload = {
        "schema_version": "1.0.0",
        "project_id": manifest.project_id,
        "project_name": manifest.project_name,
        "intake_mode": manifest.intake_mode.value,
        "scale": manifest.scale.value,
        "primary_profile": manifest.primary_profile.value,
        "profiles": [profile.value for profile in manifest.profiles],
        "repository_root": ".",
        "instruction_path": "instruction",
        "plan_path": "plan",
        "jira_path": "jira",
        "local_first": True,
        "external_writes": "DENY",
        "secret_refs_only": True,
        "compiled_from": manifest.compilation_id,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _base_templates(manifest: CompiledProjectManifest) -> dict[str, str]:
    templates = {
        ".project-pipeline/project_manifest.json": _portable_manifest_content(manifest),
        "instruction/README.md": (
            "# Project Instructions\n\n"
            "This directory is the project-specific instruction authority. Record source hierarchy, "
            "repository boundaries, verification commands, prohibited operations, and escalation rules "
            "before autonomous mutation is enabled.\n"
        ),
        "plan/README.md": (
            "# Project Plans\n\n"
            "Maintain indexed technical plans with stable identifiers, explicit requirements, decisions, "
            "risks, acceptance criteria, and implementation evidence.\n"
        ),
        "jira/README.md": (
            "# Local Work Management\n\n"
            "This directory is reserved for structured local work items and reconciliation metadata. "
            "Remote synchronization remains disabled until explicitly configured and authorized.\n"
        ),
    }
    if manifest.intake_mode is IntakeMode.EXISTING_PROJECT:
        return templates

    templates.update(
        {
            "README.md": (
                f"# {manifest.project_name}\n\n"
                "This repository was initialized through a controlled, non-destructive Project Pipeline "
                "bootstrap. See `instruction/`, `plan/`, and `jira/` before changing project authority.\n\n"
                "## Local verification\n\n"
                "Run the profile-specific commands declared in `pyproject.toml` or the selected build system.\n"
            ),
            ".gitignore": (
                ".env\n.venv/\n.local/\n__pycache__/\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\ndist/\nbuild/\n"
            ),
        }
    )
    python_profiles = {
        ProjectProfile.PYTHON_LIBRARY,
        ProjectProfile.PYTHON_SERVICE,
        ProjectProfile.MACHINE_LEARNING,
        ProjectProfile.POLYGLOT_APPLICATION,
    }
    if any(profile in python_profiles for profile in manifest.profiles):
        package = _package_name(manifest.project_name)
        templates.update(
            {
                "pyproject.toml": (
                    "[build-system]\n"
                    'requires = ["setuptools>=78,<82"]\n'
                    'build-backend = "setuptools.build_meta"\n\n'
                    "[project]\n"
                    f'name = "{package.replace("_", "-")}"\n'
                    'version = "0.1.0"\n'
                    f'description = "{manifest.project_name}"\n'
                    'requires-python = ">=3.11,<3.14"\n\n'
                    "[tool.pytest.ini_options]\n"
                    'testpaths = ["tests"]\n'
                    'pythonpath = ["src"]\n'
                ),
                f"src/{package}/__init__.py": (
                    f'"""{manifest.project_name} package."""\n\n__version__ = "0.1.0"\n'
                ),
                "tests/test_bootstrap_smoke.py": (
                    "from __future__ import annotations\n\n"
                    f"import {package}\n\n\n"
                    "def test_package_version_is_declared() -> None:\n"
                    f'    assert {package}.__version__ == "0.1.0"\n'
                ),
                ".github/workflows/ci.yml": (
                    "name: CI\n\n"
                    "on:\n"
                    "  pull_request:\n"
                    "  push:\n"
                    "    branches: [main]\n\n"
                    "permissions:\n"
                    "  contents: read\n\n"
                    "jobs:\n"
                    "  test:\n"
                    "    runs-on: ubuntu-latest\n"
                    "    timeout-minutes: 15\n"
                    "    steps:\n"
                    "      - uses: actions/checkout@v4\n"
                    "      - uses: actions/setup-python@v5\n"
                    "        with:\n"
                    "          python-version: '3.11'\n"
                    "      - run: python -m pip install pytest\n"
                    "      - run: python -m pytest -q\n"
                ),
            }
        )
    return templates


def _safe_target(root: Path, relative: str) -> Path:
    target = (root / relative).resolve(strict=False)
    if target != root and root not in target.parents:
        raise BootstrapError(f"bootstrap path escapes target root: {relative}")
    return target


def plan_bootstrap(manifest: CompiledProjectManifest) -> BootstrapPlan:
    root = Path(manifest.target_root).expanduser().resolve(strict=False)
    templates = _base_templates(manifest)
    directories = sorted(
        {
            str(parent.as_posix())
            for relative in templates
            for parent in Path(relative).parents
            if str(parent) not in {".", ""}
        },
        key=lambda value: (len(Path(value).parts), value),
    )
    actions: list[BootstrapAction] = []
    for relative in directories:
        target = _safe_target(root, relative)
        if target.exists() and not target.is_dir():
            action = BootstrapActionKind.CONFLICT
            reason = "A non-directory entry already occupies the required directory path."
        elif target.is_dir():
            action = BootstrapActionKind.SATISFIED
            reason = "Required directory already exists."
        else:
            action = BootstrapActionKind.CREATE_DIRECTORY
            reason = "Create a missing bootstrap directory without changing existing assets."
        actions.append(BootstrapAction(path=relative, action=action, reason=reason))
    for relative, content in sorted(templates.items()):
        target = _safe_target(root, relative)
        digest = _sha256_text(content)
        if target.exists() and target.is_file():
            observed = hashlib.sha256(target.read_bytes()).hexdigest()
            if observed == digest:
                action = BootstrapActionKind.SATISFIED
                reason = "Existing file exactly matches the controlled bootstrap content."
            else:
                action = BootstrapActionKind.CONFLICT
                reason = (
                    "Existing file differs; bootstrap will not overwrite human-authored content."
                )
        elif target.exists():
            action = BootstrapActionKind.CONFLICT
            reason = "A non-file entry already occupies the required file path."
        else:
            action = BootstrapActionKind.CREATE_FILE
            reason = "Create a missing bootstrap file using profile-aware deterministic content."
        actions.append(
            BootstrapAction(
                path=relative,
                action=action,
                reason=reason,
                content_sha256=digest,
            )
        )
    ordered = tuple(sorted(actions, key=lambda item: (item.path, item.action.value)))
    fingerprint = hashlib.sha256(
        json.dumps(
            [item.model_dump(mode="json") for item in ordered],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    bootstrap_id = deterministic_identifier(
        IdentifierKind.BOOTSTRAP,
        manifest.compilation_id,
        str(root),
        fingerprint,
    )
    return BootstrapPlan(
        bootstrap_id=str(bootstrap_id),
        compilation_id=manifest.compilation_id,
        project_id=manifest.project_id,
        intake_mode=manifest.intake_mode,
        target_root=str(root),
        actions=ordered,
        requires_existing_project_confirmation=(
            manifest.intake_mode is IntakeMode.EXISTING_PROJECT
        ),
        fingerprint=fingerprint,
    )


def _write_exclusive(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def execute_bootstrap(
    manifest: CompiledProjectManifest,
    *,
    apply: bool = False,
    confirm_existing: bool = False,
    actor_id: str = "actor:local-bootstrap",
    correlation_id: str = "corr:local-bootstrap",
) -> tuple[BootstrapPlan, BootstrapReceipt]:
    plan = plan_bootstrap(manifest)
    conflicts = tuple(
        action.path for action in plan.actions if action.action is BootstrapActionKind.CONFLICT
    )
    satisfied = tuple(
        action.path for action in plan.actions if action.action is BootstrapActionKind.SATISFIED
    )
    if plan.requires_existing_project_confirmation and not confirm_existing:
        return plan, BootstrapReceipt(
            bootstrap_id=plan.bootstrap_id,
            compilation_id=plan.compilation_id,
            outcome=BootstrapOutcome.REJECTED,
            target_root=plan.target_root,
            satisfied_paths=satisfied,
            conflict_paths=("EXISTING_PROJECT_CONFIRMATION_REQUIRED",),
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
    if conflicts:
        return plan, BootstrapReceipt(
            bootstrap_id=plan.bootstrap_id,
            compilation_id=plan.compilation_id,
            outcome=BootstrapOutcome.REJECTED,
            target_root=plan.target_root,
            satisfied_paths=satisfied,
            conflict_paths=conflicts,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
    if not apply:
        return plan, BootstrapReceipt(
            bootstrap_id=plan.bootstrap_id,
            compilation_id=plan.compilation_id,
            outcome=BootstrapOutcome.DRY_RUN,
            target_root=plan.target_root,
            satisfied_paths=satisfied,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )

    root = Path(plan.target_root)
    root.mkdir(parents=True, exist_ok=True)
    templates = _base_templates(manifest)
    created_files: list[Path] = []
    created_directories: list[Path] = []
    try:
        for action in plan.actions:
            target = _safe_target(root, action.path)
            if action.action is BootstrapActionKind.CREATE_DIRECTORY:
                target.mkdir(parents=False, exist_ok=False)
                created_directories.append(target)
            elif action.action is BootstrapActionKind.CREATE_FILE:
                _write_exclusive(target, templates[action.path])
                created_files.append(target)
    except Exception:
        rolled_back: list[str] = []
        for path in reversed(created_files):
            if path.exists():
                path.unlink()
                rolled_back.append(path.relative_to(root).as_posix())
        for path in reversed(created_directories):
            try:
                path.rmdir()
                rolled_back.append(path.relative_to(root).as_posix())
            except OSError:
                continue
        return plan, BootstrapReceipt(
            bootstrap_id=plan.bootstrap_id,
            compilation_id=plan.compilation_id,
            outcome=BootstrapOutcome.ROLLED_BACK,
            target_root=plan.target_root,
            satisfied_paths=satisfied,
            rolled_back_paths=tuple(sorted(rolled_back)),
            actor_id=actor_id,
            correlation_id=correlation_id,
        )

    created = tuple(
        sorted(
            [path.relative_to(root).as_posix() for path in created_directories]
            + [path.relative_to(root).as_posix() for path in created_files]
        )
    )
    return plan, BootstrapReceipt(
        bootstrap_id=plan.bootstrap_id,
        compilation_id=plan.compilation_id,
        outcome=BootstrapOutcome.APPLIED if created else BootstrapOutcome.NO_CHANGES,
        target_root=plan.target_root,
        created_paths=created,
        satisfied_paths=satisfied,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
