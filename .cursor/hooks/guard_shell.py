from __future__ import annotations

import json
import re
import sys

_GIT = (
    r"(?:"
    r"\"[^\"]*[\\/](?:git\.exe|git)\""
    r"|'[^\']*[\\/](?:git\.exe|git)'"
    r"|(?:[A-Za-z]:[^\s\"';&|]*[\\/])?(?:git\.exe|git)"
    r")"
)
_GIT_GLOBALS = (
    r"(?:\s+(?:"
    r"-C\s+(?:\"[^\"]+\"|'[^']+'|\S+)"
    r"|--git-dir(?:=|\s+)(?:\"[^\"]+\"|'[^']+'|\S+)"
    r"|--work-tree(?:=|\s+)(?:\"[^\"]+\"|'[^']+'|\S+)"
    r"|-c\s+\S+"
    r"|--no-pager"
    r"))*"
)
_GIT_CMD = rf"(?:^|[\s\"';&|]){_GIT}{_GIT_GLOBALS}\s+"
_MAIN_DEST = (
    r"(?:\+?(?:HEAD|[A-Za-z0-9._/-]+)?:)?"
    r"(?:[\"']?(?:refs/heads/)?(?:main|master)[\"']?)"
    r"(?:\s|$|[\"'])"
)
_GH = (
    r"(?:"
    r"\"[^\"]*[\\/](?:gh\.exe|hub\.exe|gh|hub)\""
    r"|'[^\']*[\\/](?:gh\.exe|hub\.exe|gh|hub)'"
    r"|(?:[A-Za-z]:[^\s\"';&|]*[\\/])?(?:gh\.exe|hub\.exe|gh|hub)"
    r")"
)

DENIED_PATTERNS = (
    re.compile(rf"(?i){_GIT_CMD}push\s+[^\r\n]*(?:--force-with-lease|--force|-f)(?:\s|=|$)"),
    re.compile(rf"(?i){_GIT_CMD}push\s+[^\r\n]*\s\+[A-Za-z0-9:/\._-]+"),
    re.compile(rf"(?i){_GIT_CMD}push\b[^\r\n]*[\s]{_MAIN_DEST}"),
    re.compile(rf"(?i){_GIT_CMD}push\s+[^\r\n]*(?:--mirror|--all)(?:\s|$)"),
    re.compile(rf"(?i)(?:^|[\s\"';&|]){_GH}\s+[^\r\n]*\s--admin(?:\s|=|$)"),
    re.compile(rf"(?i)(?:^|[\s\"';&|]){_GH}\s+[^\r\n]*\bpr\s+merge\b"),
    re.compile(rf"(?i)(?:^|[\s\"';&|]){_GH}\s+[^\r\n]*\bapi\b[^\r\n]*(?:/merge|mergePullRequest)"),
    re.compile(rf"(?i)(?:^|[\s\"';&|]){_GH}\s+merge\b"),
    re.compile(rf"(?i){_GIT_CMD}reset\s+--hard(?:\s|$)"),
    re.compile(rf"(?i){_GIT_CMD}clean\s+-\S*f"),
    re.compile(
        r"(?i)(?:^|[\s\"';&|])(?:rm|del|rmdir|remove-item)\s+[^\r\n]*(?:-r|-recurse).*?(?:-force|-f)"
    ),
    re.compile(r"(?i)(?:^|[\s\"';&|])(?:curl|wget|invoke-webrequest|invoke-restmethod)\s+"),
    re.compile(
        r"(?i)(?:type|get-content|cat)\s+[^\r\n]*(?:\.env|\.pem|\.key|credential|Github_Repo)"
    ),
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
    try:
        command = _command_from_payload(sys.stdin.read())
        if any(pattern.search(command) for pattern in DENIED_PATTERNS):
            _emit(
                "deny",
                agentMessage=(
                    "ProjectPipeline requires governed adapters for destructive, "
                    "secret-bearing, protected-main, and network commands."
                ),
                userMessage="Blocked by the ProjectPipeline Cursor shell policy.",
            )
            return 0
        _emit("allow")
        return 0
    except Exception as exc:
        _emit(
            "deny",
            agentMessage=f"shell hook failed closed: {type(exc).__name__}",
            userMessage="Blocked by the ProjectPipeline Cursor shell policy.",
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
