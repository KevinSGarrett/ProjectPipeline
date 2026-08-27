from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote

REQUIRED_PUBLIC_PATHS = (
    "README.md",
    "LICENSE",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    ".gitignore",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/pull_request_template.md",
    ".github/workflows/codeql.yml",
    ".github/workflows/quality.yml",
    "docs/assets/social-preview.jpg",
    "docs/assets/projectpipeline-hero.png",
    "docs/assets/autonomous-engineering-loop.png",
)

FORBIDDEN_PUBLIC_PATHS = (
    ".agents",
    ".claude",
    ".codex",
    ".cursor",
    ".gemini",
    ".openrouter",
    ".runpod",
    "AGENTS.md",
    "instructions",
    "jira",
    "plans",
    "evidence",
    "provenance",
    "docs/operations/CURSOR_TAKEOVER_PROMPT.md",
)

REQUIRED_IGNORE_RULES = (
    "/.agents/",
    "/.claude/",
    "/.codex*",
    "/.cursor/",
    "/.gemini/",
    "/.openrouter/",
    "/.runpod/",
    "/AGENTS.md",
    "/instructions/",
    "/jira/",
    "/plans/",
    "/evidence/",
    "/provenance/",
    "/credentials.json",
    "/secrets.json",
)

REQUIRED_README_MARKERS = (
    "# ProjectPipeline",
    "## Development status",
    "## Why ProjectPipeline?",
    "## What it does",
    "## Quick start",
    "## Architecture at a glance",
    "## Documentation",
    "## Community",
    "## License",
    "actions/workflows/quality.yml/badge.svg",
    "actions/workflows/codeql.yml/badge.svg",
    "docs/assets/projectpipeline-hero.png",
    "docs/assets/autonomous-engineering-loop.png",
)

MACHINE_SPECIFIC_MARKERS = (
    re.compile(r"C:\\Project_X\b", re.IGNORECASE),
    re.compile(r"Project_X_worktrees", re.IGNORECASE),
    re.compile(r"F:\\Models\b", re.IGNORECASE),
    re.compile(r"ProjectPipeline_ReadMe\.txt", re.IGNORECASE),
    re.compile(r"ChatGPT Image Aug 26", re.IGNORECASE),
)

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
TEXT_SUFFIXES = {".md", ".markdown", ".yml", ".yaml", ".toml", ".html"}
ROOT_PUBLIC_TEXT = {
    "README.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    "LICENSE",
}


def _tracked_paths(root: Path) -> set[str] | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return None
    return {item.replace("\\", "/") for item in result.stdout.split("\0") if item}


def forbidden_public_paths(root: Path) -> tuple[str, ...]:
    tracked = _tracked_paths(root)
    if tracked is None:
        return tuple(relative for relative in FORBIDDEN_PUBLIC_PATHS if (root / relative).exists())
    return tuple(
        relative
        for relative in FORBIDDEN_PUBLIC_PATHS
        if any(path == relative or path.startswith(f"{relative}/") for path in tracked)
    )


def _public_text_paths(root: Path) -> Iterable[Path]:
    for relative in sorted(ROOT_PUBLIC_TEXT):
        path = root / relative
        if path.is_file():
            yield path
    for directory in (".github", "docs", "runbooks"):
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                yield path


def machine_specific_references(root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    for path in _public_text_paths(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in MACHINE_SPECIFIC_MARKERS):
                relative = path.relative_to(root).as_posix()
                findings.append(f"{relative}:{line_number}")
    return tuple(findings)


def _local_markdown_link_errors(root: Path, path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for match in MARKDOWN_LINK.finditer(text):
        target = match.group(1).strip().strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        relative = unquote(target.split("#", 1)[0])
        if not relative:
            continue
        candidate = (path.parent / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            errors.append(f"{path.relative_to(root).as_posix()} link escapes repository: {target}")
            continue
        if not candidate.exists():
            errors.append(f"{path.relative_to(root).as_posix()} link target is missing: {target}")
    return errors


def readme_surface_errors(root: Path) -> tuple[str, ...]:
    readme = root / "README.md"
    if not readme.is_file():
        return ("README.md is missing",)
    text = readme.read_text(encoding="utf-8")
    errors = [
        f"README.md is missing required marker: {marker}"
        for marker in REQUIRED_README_MARKERS
        if marker not in text
    ]
    if text.count("## Development status") != 1:
        errors.append("README.md must contain exactly one Development status section")
    if len(text.splitlines()) > 300:
        errors.append("README.md exceeds the 300-line public front-page limit")
    errors.extend(_local_markdown_link_errors(root, readme))
    return tuple(errors)


def validate_public_repository_surface(root: Path) -> list[str]:
    root = root.resolve()
    errors = [
        f"required public repository path is missing: {relative}"
        for relative in REQUIRED_PUBLIC_PATHS
        if not (root / relative).exists()
    ]
    errors.extend(
        f"private maintainer path is present in public source: {relative}"
        for relative in forbidden_public_paths(root)
    )
    errors.extend(
        f"machine-specific maintainer reference is present: {location}"
        for location in machine_specific_references(root)
    )
    errors.extend(readme_surface_errors(root))

    gitignore = root / ".gitignore"
    if gitignore.is_file():
        ignore_text = gitignore.read_text(encoding="utf-8")
        errors.extend(
            f".gitignore is missing public-safety rule: {rule}"
            for rule in REQUIRED_IGNORE_RULES
            if rule not in ignore_text
        )

    asset_limits = {
        "docs/assets/social-preview.jpg": 1_000_000,
        "docs/assets/projectpipeline-hero.png": 3_000_000,
        "docs/assets/autonomous-engineering-loop.png": 3_000_000,
    }
    for relative, maximum_bytes in asset_limits.items():
        path = root / relative
        if path.is_file() and path.stat().st_size > maximum_bytes:
            errors.append(
                f"public image exceeds {maximum_bytes} bytes: {relative} ({path.stat().st_size})"
            )
    return errors
