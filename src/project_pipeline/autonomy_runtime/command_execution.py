from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PYTHON_NAMES = {"python", "python.exe", "python3", "python3.exe"}
_SHELL_METATOKENS = {";", "|", "&", "&&", "||"}
ALLOWED_MODULE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("-m", "project_pipeline", "completion"),
    ("-m", "project_pipeline", "doctor"),
    ("-m", "project_pipeline", "validate"),
    ("-m", "project_pipeline", "jira", "validate"),
    ("-m", "project_pipeline", "control", "evaluate"),
    ("-m", "project_pipeline", "control", "sequence"),
)
ALLOWED_SCRIPT_NAMES = frozenset(
    {
        "scripts/run_autonomy_qualification.py",
        "scripts/run_live_qualification.py",
        "scripts/run_autonomy_campaign.py",
        "scripts/campaign_probe.py",
    }
)
_TAIL_CHARS = 2048


def is_python_executable(value: str) -> bool:
    path = Path(value)
    if path.name.lower() in _PYTHON_NAMES:
        return True
    try:
        return path.resolve() == Path(sys.executable).resolve()
    except OSError:
        return False


def _normalized_script(argument: str, repository_root: Path) -> str:
    candidate = Path(argument)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(repository_root.resolve()).as_posix()
        except ValueError:
            return candidate.name
    return candidate.as_posix().replace("\\", "/")


def command_is_allowlisted(argv: list[str], *, repository_root: Path) -> bool:
    if not argv or not all(isinstance(item, str) for item in argv):
        return False
    if not is_python_executable(argv[0]):
        return False
    rest = argv[1:]
    if any(token in _SHELL_METATOKENS or "\n" in token for token in rest):
        return False
    for prefix in ALLOWED_MODULE_PREFIXES:
        if tuple(rest[: len(prefix)]) == prefix:
            return True
    if not rest:
        return False
    return _normalized_script(rest[0], repository_root) in ALLOWED_SCRIPT_NAMES


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def execute_allowlisted_command(
    argv: list[str],
    *,
    cwd: Path,
    repository_root: Path,
    timeout_seconds: float = 120.0,
    idempotency_key: str | None = None,
    evidence_links: list[str] | None = None,
) -> dict[str, Any]:
    if not command_is_allowlisted(argv, repository_root=repository_root):
        raise ValueError("command is not on the campaign allowlist")
    encoded = json.dumps(argv, sort_keys=True)
    started = datetime.now(UTC)
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        shell=False,
    )
    ended = datetime.now(UTC)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    key = idempotency_key or ("CIDEMP-" + hashlib.sha256(encoded.encode()).hexdigest()[:16])
    exit_code = int(completed.returncode)
    return {
        "command": list(argv),
        "command_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "cwd": str(cwd),
        "started_at_utc": started.isoformat(),
        "ended_at_utc": ended.isoformat(),
        "exit_code": exit_code,
        "stdout_sha256": _digest_text(stdout),
        "stderr_sha256": _digest_text(stderr),
        "stdout_tail": stdout[-_TAIL_CHARS:],
        "stderr_tail": stderr[-_TAIL_CHARS:],
        "result": "PASSED" if exit_code == 0 else "FAILED",
        "idempotency_key": key,
        "retry_disposition": "not-retried",
        "evidence_links": list(evidence_links or ()),
        "executed": True,
    }
