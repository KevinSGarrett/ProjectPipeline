from __future__ import annotations

import json
import re
import sys

DENIED_PATTERNS = (
    re.compile(
        r"(?i)(?:^|[\s\"';&|])git\s+(?:push|reset\s+--hard|clean\s+-\S*f|checkout\s+--)(?:\s|$)"
    ),
    re.compile(r"(?i)(?:^|[\s\"';&|])gh\s+"),
    re.compile(
        r"(?i)(?:^|[\s\"';&|])(?:rm|del|rmdir|remove-item)\s+[^\r\n]*(?:-r|-recurse|-force)"
    ),
    re.compile(
        r"(?i)(?:type|get-content|cat)\s+[^\r\n]*(?:\.env|\.pem|\.key|credential|Github_Repo)"
    ),
    re.compile(r"(?i)(?:^|[\s\"';&|])(?:curl|wget|invoke-webrequest|invoke-restmethod)\s+"),
)


def main() -> int:
    payload = json.load(sys.stdin)
    command = str(payload.get("command", ""))
    if any(pattern.search(command) for pattern in DENIED_PATTERNS):
        print(
            json.dumps(
                {
                    "permission": "deny",
                    "agentMessage": (
                        "ProjectPipeline requires governed adapters for destructive, "
                        "secret-bearing, GitHub, and network commands."
                    ),
                    "userMessage": "Blocked by the ProjectPipeline Cursor shell policy.",
                }
            )
        )
        return 0
    print(json.dumps({"permission": "allow"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
