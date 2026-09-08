"""Deterministic stdlib-only indexing job for fleet useful-work comparisons.

No GPU, no AVX2 requirement, no network, no .env. Safe to copy into a remote
``pp_jobs`` workspace and invoke as ``python useful_index.py``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time


def index_bytes(payload: bytes) -> dict[str, object]:
    started = time.perf_counter()
    digest = hashlib.sha256()
    view = memoryview(payload)
    for offset in range(0, len(payload), 65536):
        digest.update(view[offset : offset + 65536])
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "bytes": len(payload),
        "sha256": digest.hexdigest(),
        "elapsed_ms": elapsed_ms,
        "argv": list(sys.argv),
    }


def main() -> int:
    size = 8 * 1024 * 1024
    seed = b"PP-FLEET-INDEX-v1"
    payload = (seed * ((size // len(seed)) + 1))[:size]
    result = index_bytes(payload)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
