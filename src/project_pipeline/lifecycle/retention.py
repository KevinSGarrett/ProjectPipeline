from __future__ import annotations

from datetime import UTC, datetime, timedelta

from project_pipeline.domain.lifecycle import (
    ClosureReadiness,
    ProjectTerminalState,
    RetentionPolicy,
)


class InformationLifecycleManager:
    def gc_decision(
        self,
        *,
        policy: RetentionPolicy,
        created_at_utc: datetime,
        live_reference_count: int,
        legal_hold: bool = False,
        now: datetime | None = None,
    ) -> dict[str, object]:
        if live_reference_count < 0:
            raise ValueError("live_reference_count cannot be negative")
        now = now or datetime.now(UTC)
        expired = (
            False
            if policy.permanent
            else now >= created_at_utc + timedelta(days=int(policy.retention_days or 0))
        )
        eligible = expired and live_reference_count == 0 and not legal_hold
        return {
            "retention_expired": expired,
            "zero_live_references": live_reference_count == 0,
            "legal_hold": legal_hold,
            "eligible_for_gc_plan": eligible,
            "deletion_authorized": False,
            "secure_delete_required": policy.secure_delete_required,
        }


class ProjectClosureDirector:
    _CHECKS = (
        "final_requirements_verified",
        "final_release_signed",
        "jira_reconciled",
        "git_clean",
        "evidence_archive_built",
        "jira_snapshot_built",
        "handoff_built",
        "unused_resources_release_planned",
        "credentials_revocation_planned",
        "scheduled_tasks_disable_planned",
        "final_backup_restore_verified",
    )

    def readiness(self, status: ClosureReadiness) -> dict[str, object]:
        missing = [name for name in self._CHECKS if not getattr(status, name)]
        if status.legal_hold_active:
            missing.append("legal_hold_resolution")
        can_archive = status.current_state == ProjectTerminalState.CLOSING and not missing
        return {
            "project_id": status.project_id,
            "can_archive": can_archive,
            "missing": missing,
            "external_cleanup_authorized": False,
            "archive_transition_requires_typed_action": True,
        }

    def plan_archive(self, status: ClosureReadiness) -> dict[str, object]:
        check = self.readiness(status)
        return {
            **check,
            "target_state": ProjectTerminalState.ARCHIVED.value,
            "actions": [
                "freeze_final_state",
                "build_archive_manifest",
                "verify_backup_restore",
                "plan_resource_release",
                "plan_credential_revocation",
                "disable_scheduled_tasks_after_authorization",
            ],
            "live_mutation_performed": False,
        }
