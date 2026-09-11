"""Independent local worker identity. Caller-supplied host labels are not authority."""

from __future__ import annotations

import hashlib
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

_SID = re.compile(r"S-1-5-\d+(?:-\d+)+", re.IGNORECASE)


def local_hostname() -> str:
    return (os.environ.get("COMPUTERNAME") or socket.gethostname() or "").strip()


def local_principal() -> str:
    host = local_hostname()
    user = (os.environ.get("USERNAME") or os.environ.get("USER") or "").strip()
    if host and user:
        return f"{host}\\{user}"
    return user


def local_sid() -> str:
    completed = subprocess.run(
        ["whoami", "/user"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    text = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    match = _SID.search(text)
    return match.group(0) if match else ""


def module_sha256(path: str | None = None) -> str:
    raw = path or globals().get("__file__")
    if not raw:
        return ""
    try:
        return hashlib.sha256(Path(str(raw)).read_bytes()).hexdigest()
    except OSError:
        return ""


def _git_source_identity(root: Path) -> tuple[str, str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD", "HEAD^{tree}"],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    lines = [line.strip().lower() for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or len(lines) < 2:
        return "", ""
    if len(lines[0]) != 40 or len(lines[1]) != 40:
        return "", ""
    return lines[0], lines[1]


def measured_source_identity(*, protocol_file: str | None = None) -> tuple[str, str]:
    """Measure executing-worker source/tree. Envelope strings are not authority."""

    env_sha = (os.environ.get("PP_WORKER_SOURCE_SHA") or "").strip().lower()
    env_tree = (os.environ.get("PP_WORKER_SOURCE_TREE") or "").strip().lower()
    if len(env_sha) == 40 and len(env_tree) == 40:
        return env_sha, env_tree
    candidates: list[Path] = []
    worker_src = (os.environ.get("PP_WORKER_SRC") or "").strip()
    if worker_src:
        candidates.append(Path(worker_src))
    if protocol_file:
        candidates.append(Path(protocol_file))
    here = Path(__file__).resolve()
    candidates.append(here)
    seen: set[Path] = set()
    for start in candidates:
        current = start if start.is_dir() else start.parent
        while current not in seen:
            seen.add(current)
            if (current / ".git").exists() or (current / ".git").is_file():
                sha, tree = _git_source_identity(current)
                if sha and tree:
                    return sha, tree
            if current.parent == current:
                break
            current = current.parent
    return "", ""


def local_runtime_identity(*, protocol_file: str | None = None) -> dict[str, str]:
    hostname = local_hostname()
    sid = local_sid()
    principal = local_principal()
    source_sha, source_tree = measured_source_identity(protocol_file=protocol_file)
    return {
        "hostname": hostname,
        "principal": principal,
        "sid": sid,
        "module_sha256": module_sha256(protocol_file),
        "source_sha": source_sha,
        "source_tree": source_tree,
    }


def identity_matches(
    payload: dict[str, Any],
    live: dict[str, str],
    *,
    required_host: str,
) -> tuple[str, ...]:
    failures: list[str] = []
    live_host = str(live.get("hostname") or "").strip()
    if not live_host:
        failures.append("live_host_unknown")
    elif live_host.casefold() != required_host.casefold():
        failures.append("host_mismatch")
    supplied_host = str(payload.get("host_id") or "").strip()
    if not supplied_host:
        failures.append("host_missing")
    elif supplied_host.casefold() != live_host.casefold():
        failures.append("host_mismatch")
    principal = str(payload.get("principal") or "").strip()
    live_principal = str(live.get("principal") or "").strip()
    live_sid = str(live.get("sid") or "").strip()
    if not principal:
        failures.append("principal_missing")
    elif principal.casefold() not in {
        live_principal.casefold(),
        live_sid.casefold(),
    }:
        failures.append("principal_mismatch")
    if not live_sid:
        failures.append("sid_unverified")
    return tuple(failures)


def authority_identity(payload: dict[str, Any]) -> str:
    keys = (
        "job_id",
        "input_sha256",
        "source_sha",
        "source_tree",
        "overlay_sha256",
        "fence",
        "principal",
        "lease_id",
        "host_id",
    )
    body = {key: str(payload.get(key) or "") for key in keys}
    encoded = str(sorted(body.items()))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
