from __future__ import annotations

from collections import Counter

from project_pipeline.domain.assurance import (
    AttemptBudget,
    AttemptObservation,
    LoopDisposition,
    LoopGuardDecision,
    assurance_identifier,
)


def evaluate_loop(
    observations: tuple[AttemptObservation, ...], budget: AttemptBudget
) -> LoopGuardDecision:
    relevant = tuple(
        sorted(
            (o for o in observations if o.task_id == budget.task_id), key=lambda o: o.attempt_number
        )
    )
    attempts = max(budget.used_attempts, len(relevant))
    failure_counts = Counter(o.failure_signature for o in relevant if o.failure_signature)
    repeated_failure = max(failure_counts.values(), default=0)
    output_counts = Counter(o.output_fingerprint for o in relevant)
    unchanged_output = max(output_counts.values(), default=0)
    action_counts = Counter((o.action_fingerprint, o.tool_fingerprint) for o in relevant)
    repeated_action = max(action_counts.values(), default=0)
    progress = any(o.progress_units > 0 for o in relevant[-2:]) if relevant else False
    progressless_cycles = 0
    for observation in reversed(relevant):
        if observation.progress_units > 0:
            break
        progressless_cycles += 1
    recent = relevant[-budget.max_progressless_cycles :]
    recent_activity = sum(item.activity_units for item in recent)
    recent_administrative = sum(item.administrative_units for item in recent)
    administrative_ratio_milli = (
        (recent_administrative * 1000) // recent_activity if recent_activity else 0
    )
    latest_has_novelty = (
        bool(relevant[-1].novelty_dimensions)
        if len(relevant) >= 2 and relevant[-2].failure_signature
        else True
    )
    reasons: list[str] = []
    disposition = LoopDisposition.CONTINUE
    if attempts >= budget.max_attempts:
        disposition = LoopDisposition.STOP_AND_ESCALATE
        reasons.append("attempt budget exhausted")
    if repeated_failure > budget.max_same_failure:
        disposition = LoopDisposition.STOP_AND_ESCALATE
        reasons.append("same failure repeated beyond allowed recovery attempts")
    if unchanged_output > budget.max_unchanged_outputs:
        disposition = LoopDisposition.STOP_AND_ESCALATE
        reasons.append("output is unchanged across repeated attempts")
    if not latest_has_novelty and disposition is LoopDisposition.CONTINUE:
        disposition = LoopDisposition.REQUIRE_NOVELTY
        reasons.append("retry after failure does not identify a material novelty dimension")
    if repeated_action >= 2 and not progress and disposition is LoopDisposition.CONTINUE:
        disposition = LoopDisposition.REQUIRE_NOVELTY
        reasons.append("same action/tool pattern repeated without measurable progress")
    if progressless_cycles >= budget.max_progressless_cycles:
        disposition = LoopDisposition.STOP_AND_ESCALATE
        reasons.append("consecutive cycles produced no objective progress delta")
    if (
        recent_activity
        and administrative_ratio_milli > budget.max_noncritical_administrative_ratio_milli
        and not progress
        and disposition is LoopDisposition.CONTINUE
    ):
        disposition = LoopDisposition.REQUIRE_NOVELTY
        reasons.append("noncritical administrative work exceeded its budget without progress")
    if not reasons:
        reasons.append("attempt remains within budget and no cycling condition is detected")
    fingerprint_parts = [
        str(attempts),
        str(repeated_failure),
        str(unchanged_output),
        str(repeated_action),
        disposition.value,
    ]
    return LoopGuardDecision(
        decision_id=assurance_identifier("LOOP", budget.task_id, *fingerprint_parts),
        task_id=budget.task_id,
        disposition=disposition,
        attempts_used=attempts,
        repeated_failure_count=repeated_failure,
        unchanged_output_count=unchanged_output,
        repeated_action_count=repeated_action,
        progress_detected=progress,
        progressless_cycle_count=progressless_cycles,
        administrative_ratio_milli=administrative_ratio_milli,
        reasons=tuple(reasons),
    )
