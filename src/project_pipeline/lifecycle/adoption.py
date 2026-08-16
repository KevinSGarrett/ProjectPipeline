from __future__ import annotations

from project_pipeline.domain.lifecycle import AdoptionMaturity


def assess_adoption_maturity(*, project_id: str, observed: dict[str, bool]) -> AdoptionMaturity:
    """Measures adoption maturity without mutating authoritative project assets."""
    return AdoptionMaturity(
        project_id=project_id,
        discovery_complete=bool(observed.get("discovery_complete")),
        baseline_captured=bool(observed.get("baseline_captured")),
        gap_analysis_complete=bool(observed.get("gap_analysis_complete")),
        adoption_plan_approved=bool(observed.get("adoption_plan_approved")),
        controlled_bootstrap_complete=bool(observed.get("controlled_bootstrap_complete")),
        shadow_autonomy_verified=bool(observed.get("shadow_autonomy_verified")),
        limited_autonomy_verified=bool(observed.get("limited_autonomy_verified")),
        full_autonomy_eligible=bool(observed.get("full_autonomy_eligible")),
        authoritative_assets_mutated_by_assessment=False,
    )
