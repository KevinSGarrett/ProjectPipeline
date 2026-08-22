from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from project_pipeline.domain.resilience import BackupTool, RecoveryObjective, resilience_identifier
from project_pipeline.resilience.restore import (
    RestoreTargetPolicy,
    has_traversal,
    is_drive_or_share_root,
    is_unc,
)


def load_recovery_objectives(root: Path) -> tuple[RecoveryObjective, ...]:
    data = json.loads((root / "config/resilience_policy.json").read_text(encoding="utf-8"))
    objectives = tuple(
        RecoveryObjective(
            objective_id=resilience_identifier("RPO", item["domain"]),
            domain=item["domain"],
            rpo_seconds=int(item["rpo_seconds"]),
            rto_seconds=int(item["rto_seconds"]),
            backup_strategy=item["backup_strategy"],
            destructive_restore_interval_days=int(item["destructive_restore_interval_days"]),
            rationale=item["rationale"],
        )
        for item in data["recovery_objectives"]
    )
    if not objectives:
        raise ValueError("recovery policy must define at least one objective")
    domains = [objective.domain for objective in objectives]
    if len(domains) != len(set(domains)):
        raise ValueError("recovery policy defines duplicate objective domains")
    return objectives


def _is_forbidden_restore_target(target: str) -> bool:
    raw = target.strip()
    if not raw or raw in {".", "..", "root"}:
        return True
    if has_traversal(raw) or is_unc(raw):
        return True
    candidate = Path(raw)
    if not candidate.is_absolute():
        return True
    try:
        return is_drive_or_share_root(candidate)
    except OSError:
        return True


def build_integrity_manifest(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        raise ValueError("integrity manifest requires at least one entry")
    normalized_entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for entry in entries:
        path = str(entry.get("path", "")).strip()
        sha256 = str(entry.get("sha256", "")).strip().lower()
        size_bytes = int(entry.get("size_bytes", -1))
        if not path:
            raise ValueError("integrity entry path must be non-empty")
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
            raise ValueError(f"invalid sha256 for integrity entry: {path}")
        if size_bytes < 0:
            raise ValueError(f"invalid size for integrity entry: {path}")
        if path in seen_paths:
            raise ValueError(f"duplicate integrity entry path: {path}")
        seen_paths.add(path)
        normalized_entries.append(
            {
                "path": path,
                "sha256": sha256,
                "size_bytes": size_bytes,
            }
        )
    normalized_entries.sort(key=lambda item: item["path"])
    payload = json.dumps(normalized_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "entry_count": len(normalized_entries),
        "entries": normalized_entries,
        "aggregate_sha256": hashlib.sha256(payload).hexdigest(),
    }


class BackupPlanner:
    """Builds safe backup/restore command plans. It does not execute destructive or external operations."""

    def __init__(
        self,
        objectives: tuple[RecoveryObjective, ...],
        *,
        restore_policy: RestoreTargetPolicy | None = None,
    ) -> None:
        self.objectives = {o.domain: o for o in objectives}
        self.restore_policy = restore_policy

    def objective(self, domain: str) -> RecoveryObjective:
        try:
            return self.objectives[domain]
        except KeyError as exc:
            raise ValueError(f"unknown recovery domain: {domain}") from exc

    def plan_backup(self, *, domain: str, source: str, repository: str) -> dict[str, object]:
        objective = self.objective(domain)
        if not source.strip():
            raise ValueError("backup source must be non-empty")
        if not repository.strip():
            raise ValueError("backup repository must be non-empty")
        argv: tuple[str, ...]
        if domain == "canonical_state":
            tool = BackupTool.PGBACKREST
            argv = ("pgbackrest", "--stanza=project-pipeline", "backup", "--type=incr")
        else:
            tool = BackupTool.RESTIC
            argv = ("restic", "-r", repository, "backup", source)
        return {
            "domain": domain,
            "tool": tool.value,
            "argv": list(argv),
            "rpo_seconds": objective.rpo_seconds,
            "rto_seconds": objective.rto_seconds,
            "requires_credential_broker": True,
            "mutation_scope": "backup_repository_only",
            "live_execution_performed": False,
        }

    def plan_restore(
        self, *, domain: str, repository: str, isolated_target: str
    ) -> dict[str, object]:
        objective = self.objective(domain)
        if not repository.strip():
            raise ValueError("restore repository must be non-empty")
        if _is_forbidden_restore_target(isolated_target):
            raise ValueError("restore target must be an explicit isolated target")
        if self.restore_policy is not None:
            isolated_target = str(self.restore_policy.resolve(isolated_target))
        argv: tuple[str, ...]
        if domain == "canonical_state":
            tool = BackupTool.PGBACKREST
            argv = (
                "pgbackrest",
                "--stanza=project-pipeline",
                "restore",
                f"--pg1-path={isolated_target}",
            )
        else:
            tool = BackupTool.RESTIC
            argv = ("restic", "-r", repository, "restore", "latest", "--target", isolated_target)
        return {
            "domain": domain,
            "tool": tool.value,
            "argv": list(argv),
            "isolated_target": isolated_target,
            "verification_required": True,
            "backup_status_is_not_restore_status": True,
            "objective": objective.model_dump(mode="json"),
            "live_execution_performed": False,
        }

    def plan_restore_verification(
        self,
        *,
        domain: str,
        backup_id: str,
        isolated_target: str,
    ) -> dict[str, object]:
        objective = self.objective(domain)
        if not backup_id.strip():
            raise ValueError("backup_id must be non-empty")
        if _is_forbidden_restore_target(isolated_target):
            raise ValueError("verification target must be an explicit isolated target")
        if self.restore_policy is not None:
            isolated_target = str(self.restore_policy.resolve(isolated_target))
        return {
            "domain": domain,
            "backup_id": backup_id,
            "isolated_target": isolated_target,
            "verification_checks": [
                "file_presence",
                "content_hash_match",
                "schema_compatibility",
                "application_read_path",
            ],
            "failure_cases": [
                "corrupt_backup",
                "missing_artifact",
                "stale_backup",
                "partial_restore",
                "interrupted_restore",
                "duplicate_restore_request",
                "insufficient_space",
                "permission_denied",
                "locked_file",
                "unknown_outcome",
            ],
            "idempotent_retry_required": True,
            "retain_last_valid_recovery_point": True,
            "restore_result_distinct_from_backup_result": True,
            "objective": objective.model_dump(mode="json"),
            "live_execution_performed": False,
        }
