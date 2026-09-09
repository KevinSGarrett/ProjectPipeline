"""Standalone Cycle 20 remote worker. Bootstraps the reviewed protocol."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PROTOCOL_MAIN = None


def _ensure_src() -> None:
    raw = globals().get("__file__")
    if raw:
        here = Path(str(raw)).resolve()
        for parent in [here.parent, *here.parents]:
            candidate = parent / "src"
            marker = (
                candidate / "project_pipeline" / "autonomy_runtime" / "remote_worker_protocol.py"
            )
            if marker.is_file():
                sys.path.insert(0, str(candidate))
                break
    extra = os.environ.get("PP_WORKER_SRC", "").strip()
    if extra:
        sys.path.insert(0, extra)


_ensure_src()
try:
    from project_pipeline.autonomy_runtime.remote_worker_protocol import main as _PROTOCOL_MAIN
except ImportError:
    _PROTOCOL_MAIN = None


def main() -> int:
    if _PROTOCOL_MAIN is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "worker_protocol_unavailable",
                    "exit_code": 2,
                },
                sort_keys=True,
            )
        )
        return 2
    return _PROTOCOL_MAIN()


if __name__ == "__main__":
    raise SystemExit(main())
