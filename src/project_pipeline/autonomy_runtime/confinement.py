"""Canonicalize and reject unsafe worker workspaces and argv."""

from __future__ import annotations

import re
from pathlib import Path

UNSAFE_CHARS = re.compile(r'[<>|&^%\n\r\x00"`]')
UNC_PREFIXES = ("\\\\", "//", "\\\\?\\", "//?/")
DEVICE_PREFIXES = ("\\\\.\\", "//./", "\\\\?\\", "nul", "con", "aux", "prn")
XEON_MACHINE_ID = "WIN-EVSH1DN8H5O"
COMFY_MACHINE_ID = "COMFY-V4-CPU-01"
REMOTE_JOB_WORKSPACES = {
    XEON_MACHINE_ID: r"C:\Users\kines\ProjectPipeline\jobs",
    COMFY_MACHINE_ID: r"C:\Users\Windows 11\ProjectPipeline\jobs",
}


class ConfinementError(ValueError):
    """Raised when a path or argv is not confined to the approved worker root."""


def _looks_like_device(raw: str) -> bool:
    token = raw.strip().rstrip("\\/").lower()
    name = Path(token).name.lower().split(".")[0]
    return name in {"nul", "con", "aux", "prn", "com1", "lpt1"} or token.startswith(
        tuple(item.lower() for item in DEVICE_PREFIXES)
    )


def reject_unsafe_string(value: str, *, field: str) -> str:
    if not value or not str(value).strip():
        raise ConfinementError(f"{field}_empty")
    text = str(value)
    if UNSAFE_CHARS.search(text):
        raise ConfinementError(f"{field}_metacharacters")
    if any(item in text for item in ("..", "\t")):
        raise ConfinementError(f"{field}_traversal")
    lowered = text.lower()
    if lowered.startswith(UNC_PREFIXES) or lowered.startswith("\\\\"):
        raise ConfinementError(f"{field}_unc")
    if _looks_like_device(text):
        raise ConfinementError(f"{field}_device")
    return text


def confine_remote_workspace(workspace: str, *, allowed_root: str) -> str:
    """Bind a remote workspace by lexical prefix. Do not resolve it on this host."""

    reject_unsafe_string(workspace, field="workspace")
    reject_unsafe_string(allowed_root, field="workspace_root")
    work = str(workspace).replace("/", "\\").rstrip("\\")
    root = str(allowed_root).replace("/", "\\").rstrip("\\")
    work_key = work.casefold()
    root_key = root.casefold()
    if work_key != root_key and not work_key.startswith(root_key + "\\"):
        raise ConfinementError("workspace_outside_root")
    return workspace


def canonicalize_workspace(workspace: str, *, root: str, host_id: str | None = None) -> Path:
    """Require workspace to resolve inside an explicit local root without escapes."""

    reject_unsafe_string(workspace, field="workspace")
    reject_unsafe_string(root, field="workspace_root")
    root_path = Path(root)
    work_path = Path(workspace)
    if work_path.is_absolute() is False:
        work_path = root_path / work_path
    try:
        resolved_root = root_path.resolve()
        resolved_work = work_path.resolve()
    except OSError as error:
        raise ConfinementError("workspace_unresolvable") from error
    try:
        resolved_work.relative_to(resolved_root)
    except ValueError as error:
        raise ConfinementError("workspace_outside_root") from error
    if resolved_work.is_symlink() or any(
        parent.is_symlink() for parent in [resolved_work, *resolved_work.parents]
    ):
        raise ConfinementError("workspace_symlink_escape")
    if host_id and host_id not in {XEON_MACHINE_ID, COMFY_MACHINE_ID, "PRIMARY-CODEX-WORKSTATION"}:
        raise ConfinementError("unknown_host")
    return resolved_work


def argv_is_confined(argv: tuple[str, ...] | list[str]) -> bool:
    if not argv or any(not item or "\x00" in item for item in argv):
        return False
    return all(UNSAFE_CHARS.search(item) is None for item in argv)
