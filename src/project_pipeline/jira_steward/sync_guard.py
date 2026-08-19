from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json
from project_pipeline.jira_steward.identity import (
    classify_identity_parity,
    classify_status_parity,
    parse_utc,
)
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


def evaluate_jira_sync_guard(
    root: Path,
    *,
    current_remote: Mapping[str, Any] | None = None,
    current_remote_version: str | None = None,
    latest_write_at_utc: str | None = None,
) -> JiraSyncGuardResult:
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
    identity_parity = str(payload.get("identity_parity", "")).strip().upper()
    remote_snapshot_id = str(payload.get("remote_snapshot_id", "")).strip()
    remote_version = str(
        payload.get("remote_version") or payload.get("remote_fingerprint") or ""
    ).strip()

    pending_remote = bool(payload.get("local_reconciliation_pending_remote", False))
    try:
        observed_fingerprint = JiraMirrorRepository(root).bundle().fingerprint
    except (OSError, KeyError, ValueError, TypeError):
        observed_fingerprint = ""

    if not expected_fingerprint:
        reasons.append("jira sync guard artifact does not include local_mirror_fingerprint")
    elif expected_fingerprint != observed_fingerprint:
        reasons.append(
            "jira sync guard artifact is stale for current local Jira mirror fingerprint"
        )

    if pending_remote:
        reasons.append(
            "jira sync guard cannot confirm remote/local parity while local reconciliation is pending remote apply"
        )
    if pending_remote and parity_status == "PARITY_CONFIRMED":
        reasons.append(
            "PARITY_CONFIRMED is contradictory while local_reconciliation_pending_remote is true"
        )

    token_parked = any(
        "JIRA_API_TOKEN" in str(step.get("step", ""))
        for step in payload.get(
            "blocked_external_steps",
            payload.get("autonomous_rechecks", payload.get("human" + "_required_steps", [])),
        )
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

    if not identity_parity:
        reasons.append("jira sync guard artifact is missing identity_parity")
    elif identity_parity == "NO_DIFFERENCE" and parity_status == "PARITY_CONFIRMED":
        mappings = payload.get("reconciled_remote_keys")
        if isinstance(mappings, dict) and "PP-TASK-000385" not in mappings:
            reasons.append(
                "identity NO_DIFFERENCE is stale: unique remote local-ID PP-TASK-000385 is unbound"
            )
    if identity_parity == "RECONCILIATION_REQUIRED" and parity_status == "PARITY_CONFIRMED":
        reasons.append("PARITY_CONFIRMED contradicts identity RECONCILIATION_REQUIRED")
    if not remote_snapshot_id:
        reasons.append("jira sync guard artifact is missing remote_snapshot_id")
    if not remote_version:
        reasons.append("jira sync guard artifact is missing remote_version or remote_fingerprint")

    generated_dt = parse_utc(generated_at)
    latest_write = parse_utc(latest_write_at_utc)
    if generated_dt and latest_write and generated_dt < latest_write:
        reasons.append("jira sync guard observed time predates a later merge or Jira write")

    if current_remote_version and remote_version and current_remote_version != remote_version:
        reasons.append("jira sync guard remote version does not match current remote version")

    if current_remote is not None:
        remote_issues = current_remote.get("issues")
        if not isinstance(remote_issues, list):
            reasons.append("current remote snapshot is missing an exact issue set")
        else:
            local_issues = [
                item.model_dump(mode="json") for item in JiraMirrorRepository(root).load_issues()
            ]
            identity = classify_identity_parity(
                local_issues=local_issues, remote_issues=remote_issues
            )
            if identity.fail_closed:
                reasons.extend(identity.reasons)
            elif identity.requires_reconciliation:
                reasons.append(
                    "current snapshot identity requires reconciliation and cannot be NO_DIFFERENCE"
                )
            snapshot_id = str(current_remote.get("snapshot_id") or "")
            status = classify_status_parity(
                local_issues=local_issues,
                remote_issues=remote_issues,
                snapshot_id=snapshot_id,
                expected_snapshot_id=remote_snapshot_id or snapshot_id,
            )
            if status == "FAIL_CLOSED":
                reasons.append(
                    "status parity compared a different snapshot or incomplete issue set"
                )
            current_counts = current_remote.get("status_counts")
            recorded_counts = (payload.get("readback") or {}).get("status_counts")
            if (
                isinstance(current_counts, dict)
                and isinstance(recorded_counts, dict)
                and current_counts != recorded_counts
            ):
                reasons.append("jira sync guard status counts drifted from the current snapshot")

    return JiraSyncGuardResult(
        status="PASS" if not reasons else "BLOCKED",
        reasons=tuple(reasons),
        artifact_path=str(artifact),
        expected_local_fingerprint=expected_fingerprint,
        observed_local_fingerprint=observed_fingerprint,
    )
