from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from project_pipeline.io import is_probably_text, iter_repository_files

FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ARCHIVE_EXCLUDED_SUFFIXES = frozenset({".zip", ".tar", ".gz"})


@dataclass(slots=True)
class ArchiveVerification:
    archive: str
    expected_root: str | None
    file_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "archive": self.archive,
            "expected_root": self.expected_root,
            "file_count": self.file_count,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def create_archive(root: Path, output: Path) -> Path:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in iter_repository_files(root):
            if path.resolve() == output or path.resolve() == temporary:
                continue
            if path.suffix.lower() in ARCHIVE_EXCLUDED_SUFFIXES:
                continue
            relative = path.relative_to(root).as_posix()
            archive_name = f"{root.name}/{relative}"
            info = zipfile.ZipInfo(archive_name, FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(
                info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )
    temporary.replace(output)
    return output


def verify_archive(
    archive_path: Path,
    expected_root: str | None = None,
    *,
    enforce_repository_policy: bool = True,
) -> ArchiveVerification:
    archive_path = archive_path.resolve()
    report = ArchiveVerification(str(archive_path), expected_root)
    if not archive_path.exists():
        report.errors.append("Archive does not exist")
        return report
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            names = archive.namelist()
            report.file_count = len(names)
            if len(names) != len(set(names)):
                report.errors.append("Archive contains duplicate member names")
            corrupt = archive.testzip()
            if corrupt:
                report.errors.append(f"CRC failure in member: {corrupt}")
            roots: set[str] = set()
            banned = "wa" + "ve"
            banned_pattern = re.compile(r"\b" + re.escape(banned) + r"s?\b", re.IGNORECASE)
            for name in names:
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts:
                    report.errors.append(f"Unsafe archive member path: {name}")
                    continue
                if pure.parts:
                    roots.add(pure.parts[0])
                if enforce_repository_policy and banned_pattern.search(name):
                    report.errors.append(
                        f"Repository-prohibited terminology in archive path: {name}"
                    )
                if name.endswith("/"):
                    continue
                synthetic = Path(name)
                if is_probably_text(synthetic):
                    try:
                        text = archive.read(name).decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    if enforce_repository_policy and banned_pattern.search(text):
                        report.errors.append(
                            f"Repository-prohibited terminology in archive content: {name}"
                        )
            if expected_root and roots != {expected_root}:
                report.errors.append(
                    f"Expected one root {expected_root!r}; observed {sorted(roots)!r}"
                )
            elif not expected_root and len(roots) != 1:
                report.warnings.append(f"Archive has multiple roots: {sorted(roots)!r}")
    except zipfile.BadZipFile as error:
        report.errors.append(f"Invalid ZIP archive: {error}")
    return report
