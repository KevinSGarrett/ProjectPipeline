from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DENIED_PATTERNS = (
    re.compile(r"(?i)(?:^|[\s\"';&|])git\s+push\s+[^\r\n]*(?:--force|-f)(?:\s|$)"),
    re.compile(r"(?i)(?:^|[\s\"';&|])git\s+reset\s+--hard(?:\s|$)"),
    re.compile(r"(?i)(?:^|[\s\"';&|])git\s+clean\s+-\S*f"),
    re.compile(r"(?i)(?:type|get-content|cat)\s+[^\r\n]*(?:\.env|\.pem|\.key|credential|Github_Repo)"),
)


def _emit(permission: str, **extra: str) -> None:
    print(json.dumps({"permission": permission, **extra}, ensure_ascii=False))


def _command_from_payload(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, dict):
        return str(payload.get("command") or payload.get("commandLine") or "")
    return text


def main() -> int:
    raw = sys.stdin.read()
    try:
        command = _command_from_payload(raw)
        if any(pattern.search(command) for pattern in DENIED_PATTERNS):
            _emit(
                "deny",
                agentMessage=(
                    "ProjectPipeline blocks force-push, hard reset, "
                    "broad git clean, and secret-bearing reads."
                ),
                userMessage="Blocked by the ProjectPipeline Cursor shell policy.",
            )
            return 0
        _emit("allow")
        return 0
    except Exception as exc:  # noqa: BLE001
        log_path = Path("C:/Project_X/.local/state/cursor/guard_shell_error.json")
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                json.dumps({"error": type(exc).__name__, "stdin_bytes": len(raw)}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        _emit("allow")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
