from __future__ import annotations

from project_pipeline.domain.lifecycle import (
    PlatformReleaseCandidate,
    QualificationState,
    VersionQualification,
)


class VersionQualificationManager:
    def observe_new_version(
        self, *, subject_kind: str, subject_id: str, version: str, compatibility_profile: str
    ) -> VersionQualification:
        from project_pipeline.domain.lifecycle import lifecycle_identifier

        return VersionQualification(
            qualification_id=lifecycle_identifier("QUAL", subject_kind, subject_id, version),
            subject_kind=subject_kind,
            subject_id=subject_id,
            version=version,
            state=QualificationState.QUALIFICATION,
            compatibility_profile=compatibility_profile,
            high_risk_routing_allowed=False,
        )

    def promote(
        self,
        record: VersionQualification,
        *,
        conformance_evidence_ids: tuple[str, ...],
        shadow_or_canary_evidence_ids: tuple[str, ...],
    ) -> VersionQualification:
        if not conformance_evidence_ids or not shadow_or_canary_evidence_ids:
            raise ValueError("conformance and shadow/canary evidence are required")
        return record.model_copy(
            update={
                "state": QualificationState.ACTIVE,
                "evidence_ids": tuple(
                    dict.fromkeys(
                        (
                            *record.evidence_ids,
                            *conformance_evidence_ids,
                            *shadow_or_canary_evidence_ids,
                        )
                    )
                ),
                "high_risk_routing_allowed": True,
            }
        )


class PlatformUpgradeGovernor:
    def eligibility(self, candidate: PlatformReleaseCandidate) -> dict[str, object]:
        reasons = []
        if len(candidate.artifact_sha256) != 64:
            reasons.append("separately verified release artifact sha256 is required")
        if not candidate.synthetic_e2e_certification_evidence_ids:
            reasons.append("synthetic end-to-end certification evidence is required")
        if not candidate.canary_or_shadow_evidence_ids:
            reasons.append("canary or shadow evidence is required")
        if not candidate.rollback_plan_id:
            reasons.append("rollback plan is required")
        if not candidate.migration_plan_id:
            reasons.append("migration plan is required")
        return {
            "eligible_to_control_real_projects": not reasons,
            "reasons": reasons,
            "active_platform_replacement_performed": False,
            "rollback_plan_id": candidate.rollback_plan_id,
            "post_upgrade_verification_plan_id": candidate.post_upgrade_verification_plan_id,
        }
