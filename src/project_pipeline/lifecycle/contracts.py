from __future__ import annotations

from project_pipeline.domain.lifecycle import ContractEvolution, ContractPhase


class ContractEvolutionManager:
    _ORDER = (
        ContractPhase.EXPAND,
        ContractPhase.MIGRATE,
        ContractPhase.VERIFY,
        ContractPhase.CONTRACT,
    )

    def can_advance(self, evolution: ContractEvolution, target: ContractPhase) -> dict[str, object]:
        current = self._ORDER.index(evolution.phase)
        desired = self._ORDER.index(target)
        reasons = []
        if desired != current + 1:
            reasons.append("only one forward phase transition is allowed")
        if target == ContractPhase.VERIFY and evolution.incompatible_consumers:
            reasons.append("incompatible consumers remain")
        if target == ContractPhase.CONTRACT:
            if evolution.incompatible_consumers:
                reasons.append("incompatible consumers remain")
            if not evolution.verification_evidence_ids:
                reasons.append("verification evidence is required before contract removal")
        return {
            "allowed": not reasons,
            "reasons": reasons,
            "migration_plan_id": evolution.migration_plan_id,
            "rollback_plan_id": evolution.rollback_plan_id,
            "automatic_breaking_change": False,
        }
