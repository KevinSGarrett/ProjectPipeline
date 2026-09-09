"""Fixed remote worker entrypoint. Reads a JSON envelope from stdin."""

from __future__ import annotations

from project_pipeline.autonomy_runtime.remote_worker_protocol import main, run_envelope

__all__ = ["main", "run_envelope"]


if __name__ == "__main__":
    raise SystemExit(main())
