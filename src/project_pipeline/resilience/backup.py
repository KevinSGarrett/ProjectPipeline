from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.domain.resilience import BackupTool, RecoveryObjective, resilience_identifier


def load_recovery_objectives(root: Path) -> tuple[RecoveryObjective, ...]:
    data = json.loads((root / "config/resilience_policy.json").read_text(encoding="utf-8"))
    return tuple(
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


class BackupPlanner:
    """Builds safe backup/restore command plans. It does not execute destructive or external operations."""

    def __init__(self, objectives: tuple[RecoveryObjective, ...]) -> None:
        self.objectives = {o.domain: o for o in objectives}

    def objective(self, domain: str) -> RecoveryObjective:
        try:
            return self.objectives[domain]
        except KeyError as exc:
            raise ValueError(f"unknown recovery domain: {domain}") from exc

    def plan_backup(self, *, domain: str, source: str, repository: str) -> dict[str, object]:
        objective = self.objective(domain)
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
        if not isolated_target or isolated_target in {"/", "C:\\"}:
            raise ValueError("restore target must be an explicit isolated target")
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
