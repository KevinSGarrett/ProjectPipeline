from __future__ import annotations

from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPolicy,
    ContextSelection,
    DelegationEnvelope,
)


class ContextBroker:
    """Deterministically chooses only delegation-requested context keys."""

    def select(
        self,
        envelope: DelegationEnvelope,
        candidates: tuple[ContextCandidate, ...],
        policy: ContextPolicy,
    ) -> ContextSelection:
        by_key = {c.context_key: c for c in candidates}
        required = list(envelope.required_context_keys)
        optional = list(envelope.optional_context_keys)
        unknown = [k for k in [*required, *optional] if k not in by_key]
        selected = [k for k in required if k in by_key]
        max(0, policy.max_items - len(selected))
        selected.extend(
            k
            for k in optional
            if k in by_key and k not in selected and len(selected) < policy.max_items
        )
        omitted = [k for k in optional if k in by_key and k not in selected]
        return ContextSelection(
            delegation_id=envelope.delegation_id,
            selected_keys=tuple(selected),
            omitted_keys=tuple(omitted),
            unknown_keys=tuple(unknown),
            selection_reason=(
                "REQUIRED_KEYS_FIRST",
                "OPTIONAL_KEYS_IN_DECLARED_ORDER",
                "NO_UNREQUESTED_CONTEXT",
            ),
        )
