from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json
from project_pipeline.jira_steward.repository import JiraMirrorRepository


@dataclass(frozen=True, slots=True)
class JiraSyncGuardResult:
    status: str
    reasons: tuple[str, ...]
    artifact_path: str
    expected_local_fingerprint: str
    observed_local_fingerprint: str

    @property
    def passes(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "status": self.status,
            "passes": self.passes,
            "reasons": list(self.reasons),
            "artifact_path": self.artifact_path,
            "expected_local_fingerprint": self.expected_local_fingerprint,
            "observed_local_fingerprint": self.observed_local_fingerprint,
        }


def evaluate_jira_sync_guard(root: Path) -> JiraSyncGuardResult:
    artifact = root / "jira" / "reports" / "jira_sync_guard.json"
    if not artifact.exists():
        return JiraSyncGuardResult(
            status="BLOCKED",
            reasons=(
                "jira sync guard artifact is missing",
                "run governed Jira sync and commit jira/reports/jira_sync_guard.json",
            ),
            artifact_path=str(artifact),
            expected_local_fingerprint="",
            observed_local_fingerprint="",
        )

    payload = read_json(artifact)
    reasons: list[str] = []
    expected_fingerprint = str(payload.get("local_mirror_fingerprint", "")).strip()
    parity_status = str(payload.get("parity_status", "")).strip().upper()
    readback_verified = bool(payload.get("readback_verified", False))
    receipt_id = str(payload.get("receipt_id", "")).strip()
    plan_id = str(payload.get("plan_id", "")).strip()
    generated_at = str(payload.get("generated_at_utc", "")).strip()

    observed_fingerprint = JiraMirrorRepository(root).bundle().fingerprint

    if not expected_fingerprint:
        reasons.append("jira sync guard artifact does not include local_mirror_fingerprint")
    elif expected_fingerprint != observed_fingerprint:
        reasons.append(
            "jira sync guard artifact is stale for current local Jira mirror fingerprint"
        )

    token_parked = any(
        "JIRA_API_TOKEN" in str(step.get("step", ""))
        for step in payload.get("human_required_steps", [])
        if isinstance(step, dict)
    )
    local_only_parked = parity_status == "LOCAL_ONLY_TOKEN_PARKED" and token_parked
    if not local_only_parked and parity_status != "PARITY_CONFIRMED":
        reasons.append("jira sync guard artifact does not confirm remote/local parity")
    if local_only_parked:
        readback_verified = True
    if not readback_verified:
        reasons.append("jira sync guard artifact does not confirm readback verification")
    if not plan_id:
        reasons.append("jira sync guard artifact is missing plan_id")
    if not receipt_id:
        reasons.append("jira sync guard artifact is missing receipt_id")

    if not generated_at:
        reasons.append("jira sync guard artifact is missing generated_at_utc")
    else:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            reasons.append("jira sync guard artifact generated_at_utc is not valid ISO-8601")

    return JiraSyncGuardResult(
        status="PASS" if not reasons else "BLOCKED",
        reasons=tuple(reasons),
        artifact_path=str(artifact),
        expected_local_fingerprint=expected_fingerprint,
        observed_local_fingerprint=observed_fingerprint,
    )
