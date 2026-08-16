from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote

from project_pipeline.io import is_probably_text, iter_repository_files
from project_pipeline.validation.models import ValidationReport

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
ENV_TEMPLATE_NAMES = frozenset({".env.example", ".env.sample", ".env.template"})


def is_local_env_file(relative: str) -> bool:
    name = Path(relative).name
    return name == ".env" or (name.startswith(".env.") and name not in ENV_TEMPLATE_NAMES)


def check_forbidden_terminology(
    root: Path, policy: dict[str, object], report: ValidationReport
) -> None:
    parts = policy.get("forbidden_term_parts", [])
    if not isinstance(parts, list) or not all(isinstance(item, str) for item in parts):
        report.add(
            "ERROR",
            "POLICY001",
            "Forbidden-term policy is malformed",
            "config/repository_policy.json",
        )
        return
    token = "".join(parts)
    suffix = str(policy.get("forbidden_term_plural_suffix", ""))
    pattern = re.compile(r"\b" + re.escape(token) + re.escape(suffix) + r"?\b", re.IGNORECASE)
    for path in iter_repository_files(root):
        relative = path.relative_to(root).as_posix()
        if is_local_env_file(relative):
            continue
        if pattern.search(relative):
            report.add(
                "ERROR", "TERM001", "Repository-prohibited terminology appears in a path", relative
            )
        if not is_probably_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            report.add("WARNING", "TEXT001", "Text-like file is not valid UTF-8", relative)
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                report.add(
                    "ERROR",
                    "TERM002",
                    "Repository-prohibited terminology appears in content",
                    relative,
                    number,
                )


def check_placeholders(
    root: Path,
    report: ValidationReport,
    *,
    excluded_roots: Iterable[str] = (),
) -> None:
    excluded = {item for item in excluded_roots if item}
    marker_one = "TO" + "DO"
    marker_two = "FIX" + "ME"
    marker_three = "Not" + "Implemented" + "Error"
    marker_four = "assert" + " True"
    patterns = [
        ("PLACE001", re.compile(r"\b" + marker_one + r"\b"), "Unresolved implementation marker"),
        ("PLACE002", re.compile(r"\b" + marker_two + r"\b"), "Unresolved repair marker"),
        ("PLACE003", re.compile(r"\b" + marker_three + r"\b"), "Unimplemented exception marker"),
        ("PLACE004", re.compile(re.escape(marker_four)), "Non-behavioral assertion marker"),
        ("PLACE005", re.compile(r"^\s*pass\s*(?:#.*)?$"), "Empty Python statement"),
    ]
    scan_suffixes = {".py", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml"}
    for path in iter_repository_files(root):
        relative = path.relative_to(root).as_posix()
        if path.relative_to(root).parts and path.relative_to(root).parts[0] in excluded:
            continue
        if path.stat().st_size == 0:
            report.add("ERROR", "PLACE000", "Empty file", relative)
            continue
        if path.suffix.lower() not in scan_suffixes:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            for code, pattern, message in patterns:
                if pattern.search(line):
                    report.add("ERROR", code, message, relative, number)


def check_secrets(root: Path, report: ValidationReport) -> None:
    patterns = [
        ("SECRET001", re.compile("AK" + "IA" + r"[0-9A-Z]{16}"), "Possible AWS access key"),
        ("SECRET002", re.compile("gh" + r"[pousr]_[A-Za-z0-9]{30,}"), "Possible GitHub token"),
        ("SECRET003", re.compile("xox" + r"[abprs]-[A-Za-z0-9-]{20,}"), "Possible Slack token"),
        (
            "SECRET004",
            re.compile("BEGIN " + r"(?:RSA |EC |OPENSSH )?" + "PRIVATE KEY"),
            "Possible private key material",
        ),
        (
            "SECRET005",
            re.compile(
                r"(?i)\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\b"
                r"\s*[:=]\s*[\"'][^\"']{8,}[\"']"
            ),
            "Possible hard-coded credential",
        ),
    ]
    for path in iter_repository_files(root):
        if not is_probably_text(path):
            continue
        relative = path.relative_to(root).as_posix()
        if is_local_env_file(relative):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            if relative == ".env.example" and line.rstrip().endswith("="):
                continue
            for code, pattern, message in patterns:
                if pattern.search(line):
                    report.add("ERROR", code, message, relative, number)


def check_markdown_links(root: Path, report: ValidationReport) -> None:
    for path in iter_repository_files(root):
        if path.suffix.lower() != ".md":
            continue
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            for match in MARKDOWN_LINK.finditer(line):
                raw = match.group(1).strip().split()[0].strip("<>")
                if raw.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target_text = unquote(raw.split("#", 1)[0])
                if not target_text:
                    continue
                target = (path.parent / target_text).resolve()
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    report.add(
                        "ERROR", "LINK001", f"Link escapes repository: {raw}", relative, number
                    )
                    continue
                if not target.exists():
                    report.add("ERROR", "LINK002", f"Broken internal link: {raw}", relative, number)
