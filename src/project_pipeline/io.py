from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

DEFAULT_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        ".local",
        ".codex",
        ".codex_backups",
        ".claude",
        ".cache",
        ".direnv",
        ".eggs",
        ".fleet",
        ".hypothesis",
        ".idea",
        ".ipynb_checkpoints",
        ".next",
        ".nox",
        ".npm",
        ".nuxt",
        ".parcel-cache",
        ".pnpm-store",
        ".svelte-kit",
        ".terraform",
        ".tox",
        ".vite",
        ".vs",
        ".vscode",
        "Github_Repo",
        "__pycache__",
        "blob-report",
        "build",
        "dist",
        "env",
        "ENV",
        "htmlcov",
        "node_modules",
        "pip-wheel-metadata",
        "playwright-report",
        "test-results",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".secrets",
    }
)


def _is_ignored_directory(name: str, ignored_directories: frozenset[str]) -> bool:
    return name in ignored_directories or name.startswith(".codex") or name.endswith(".egg-info")


def _is_ignored_file(name: str) -> bool:
    lower = name.lower()
    return (
        name == ".coverage"
        or name.startswith(".coverage.")
        or lower == "coverage.xml"
        or (lower.startswith("junit") and lower.endswith(".xml"))
        or lower.endswith((".prof", ".pyc", ".pyo"))
    )


def _is_shared_cursor_path(relative: Path) -> bool:
    value = relative.as_posix()
    if value in {
        ".cursor/cli.json",
        ".cursor/hooks.json",
        ".cursor/environment.json",
        ".cursor/mcp.example.json",
        ".cursor/hooks/guard_shell.py",
        ".cursor/hooks/continue-cycle.py",
    }:
        return True
    return (
        len(relative.parts) >= 3
        and relative.parts[:2] == (".cursor", "rules")
        and relative.suffix == ".mdc"
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_jsonl(path: Path) -> list[Any]:
    rows: list[Any] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL at {path}:{number}: {error}") from error
    return rows


def write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_canonical_file(path: Path) -> str:
    """Hash file bytes with UTF-8 CRLF/CR normalized to LF.

    Binary content and non-UTF-8 files are hashed unchanged. Text evidence and
    other host-checked artifacts must bind to git-canonical LF bytes so Windows
    ``core.autocrlf`` checkouts do not diverge from Linux CI.
    """
    content = path.read_bytes()
    if b"\0" not in content and _utf8_text(content):
        content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def _utf8_text(content: bytes) -> bool:
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def iter_repository_files(
    root: Path,
    *,
    ignored_directories: frozenset[str] = DEFAULT_IGNORED_DIRECTORIES,
    excluded_relative_paths: frozenset[str] = frozenset(),
) -> Iterator[Path]:
    root = root.resolve()
    candidates: list[Path] = []
    for current_root, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        directory_names[:] = sorted(
            (
                name
                for name in directory_names
                if not _is_ignored_directory(name, ignored_directories)
            ),
            key=str.lower,
        )
        current = Path(current_root)
        candidates.extend(
            current / name
            for name in sorted(file_names, key=str.lower)
            if not _is_ignored_file(name)
        )

    for path in sorted(candidates, key=lambda item: item.as_posix().lower()):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0].startswith(".codex"):
            continue
        if (
            relative.parts
            and relative.parts[0] == ".cursor"
            and not _is_shared_cursor_path(relative)
        ):
            continue
        if relative.parts and relative.parts[0] == "state":
            continue
        if relative.as_posix() in excluded_relative_paths:
            continue
        yield path


def is_probably_text(path: Path) -> bool:
    return path.suffix.lower() in {
        "",
        ".md",
        ".txt",
        ".py",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".csv",
        ".sh",
        ".ps1",
        ".bat",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".tsx",
        ".sql",
        ".env",
        ".example",
    }
