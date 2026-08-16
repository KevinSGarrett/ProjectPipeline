from __future__ import annotations

from project_pipeline.domain.assurance import (
    ScopeChangeDecision,
    ScopeChangeDisposition,
    ScopeContract,
    assurance_identifier,
)


def evaluate_scope_change(
    contract: ScopeContract,
    *,
    requested_behavior: tuple[str, ...] = (),
    requested_paths: tuple[str, ...] = (),
) -> ScopeChangeDecision:
    allowed_paths = set(contract.allowed_paths)
    outside_paths = [
        path
        for path in requested_paths
        if allowed_paths
        and not any(path == p or path.startswith(p.rstrip("/") + "/") for p in allowed_paths)
    ]
    included = set(contract.included_behavior)
    new_behavior = [item for item in requested_behavior if item not in included]
    material = bool(outside_paths or new_behavior)
    remaining = max(0, contract.change_budget - contract.consumed_changes)
    reasons: list[str] = []
    if not material:
        disposition = ScopeChangeDisposition.WITHIN_FROZEN_SCOPE
        reasons.append("requested work remains inside the frozen behavior/path boundary")
    elif remaining <= 0:
        disposition = ScopeChangeDisposition.CHANGE_BUDGET_EXHAUSTED
        reasons.append("autonomous change budget is exhausted")
    else:
        disposition = ScopeChangeDisposition.REQUIRE_REVIEW
        if new_behavior:
            reasons.append(f"{len(new_behavior)} requested behaviors are outside frozen scope")
        if outside_paths:
            reasons.append(
                f"{len(outside_paths)} requested paths are outside the allowed path boundary"
            )
    return ScopeChangeDecision(
        change_id=assurance_identifier(
            "SCHANGE",
            contract.scope_id,
            "|".join(requested_behavior) or "<none>",
            "|".join(requested_paths) or "<none>",
        ),
        scope_id=contract.scope_id,
        disposition=disposition,
        requested_behavior=requested_behavior,
        requested_paths=requested_paths,
        material=material,
        remaining_change_budget=remaining,
        reasons=tuple(reasons),
    )
