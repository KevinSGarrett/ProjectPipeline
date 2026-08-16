from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.io import sha256_file


def evidence_record(
    *,
    evidence_id: str,
    claim: str,
    artifact_path: str,
    root: Path,
    method: str,
    result: str,
    verification_status: str,
    requirement_ids: list[str] | None = None,
    criterion_ids: list[str] | None = None,
    environment: str = "local_build_environment",
) -> dict[str, Any]:
    artifact = root / artifact_path
    if not artifact.exists():
        raise FileNotFoundError(artifact)
    return {
        "schema_version": "1.0.0",
        "evidence_id": evidence_id,
        "claim": claim,
        "requirement_ids": requirement_ids or [],
        "criterion_ids": criterion_ids or [],
        "method": method,
        "artifact_path": artifact_path,
        "sha256": sha256_file(artifact),
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "environment": environment,
        "result": result,
        "verification_status": verification_status,
        "supersedes": None,
    }
