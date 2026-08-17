from datetime import UTC, datetime

from project_pipeline.assurance.loop_guard import evaluate_loop
from project_pipeline.assurance.scope import evaluate_scope_change
from project_pipeline.domain.assurance import (
    AttemptBudget,
    AttemptObservation,
    LoopDisposition,
    ScopeChangeDisposition,
    ScopeContract,
    assurance_fingerprint,
    assurance_identifier,
)


def obs(n, *, failure="same", output="same", action="same", progress=0, novelty=()):
    return AttemptObservation(
        task_id="PP-TASK-X",
        attempt_number=n,
        action_fingerprint=assurance_fingerprint(("a", action)),
        tool_fingerprint=assurance_fingerprint(("tool", action)),
        output_fingerprint=assurance_fingerprint(("out", output)),
        state_fingerprint=assurance_fingerprint(("state", n, progress)),
        failure_signature=failure,
        novelty_dimensions=tuple(novelty),
        progress_units=progress,
    )


def budget(**kw):
    data = dict(
        task_id="PP-TASK-X",
        max_attempts=5,
        used_attempts=0,
        max_same_failure=2,
        max_unchanged_outputs=2,
        max_progressless_cycles=3,
    )
    data.update(kw)
    return AttemptBudget(**data)


def scope(**kw):
    data = dict(
        scope_id=assurance_identifier("SCOPE", "PP-TASK-X", "frozen"),
        work_item_id="PP-TASK-X",
        included_behavior=("implement assurance",),
        excluded_behavior=("redesign unrelated UI",),
        allowed_paths=("src/project_pipeline/assurance", "tests"),
        escalation_conditions=("new behavior", "outside path"),
        frozen_criteria_fingerprint="a" * 64,
        change_budget=2,
        consumed_changes=0,
        frozen_at_utc=datetime(2026, 8, 15, tzinfo=UTC),
    )
    data.update(kw)
    return ScopeContract(**data)


def test_attempt_budget_exhaustion_escalates():
    decision = evaluate_loop(
        tuple(
            obs(i, failure=str(i), output=str(i), action=str(i), progress=1) for i in range(1, 6)
        ),
        budget(used_attempts=5),
    )
    assert decision.disposition is LoopDisposition.STOP_AND_ESCALATE


def test_repeated_failure_escalates():
    decision = evaluate_loop(tuple(obs(i) for i in range(1, 4)), budget())
    assert decision.disposition is LoopDisposition.STOP_AND_ESCALATE
    assert decision.repeated_failure_count == 3


def test_repeated_action_without_progress_requires_novelty_before_hard_limit():
    decision = evaluate_loop(
        (obs(1, failure="a", output="a"), obs(2, failure="b", output="b")), budget()
    )
    assert decision.disposition is LoopDisposition.REQUIRE_NOVELTY


def test_loop_guard_stops_consecutive_progressless_administrative_cycles():
    observations = tuple(
        obs(index).model_copy(update={"activity_units": 10, "administrative_units": 10})
        for index in range(1, 3)
    )

    decision = evaluate_loop(observations, budget(max_progressless_cycles=2))

    assert decision.disposition is LoopDisposition.STOP_AND_ESCALATE
    assert decision.progressless_cycle_count == 2
    assert decision.administrative_ratio_milli == 1000
    assert any("no objective progress delta" in reason for reason in decision.reasons)


def test_recent_progress_allows_continue_when_no_hard_limit_hit():
    decision = evaluate_loop(
        (
            obs(1, failure="a", output="a"),
            obs(2, failure="b", output="b", progress=1, novelty=("HYPOTHESIS",)),
        ),
        budget(),
    )
    assert decision.disposition is LoopDisposition.CONTINUE
    assert decision.progress_detected is True


def test_scope_change_inside_frozen_boundary_is_allowed():
    decision = evaluate_scope_change(
        scope(),
        requested_behavior=("implement assurance",),
        requested_paths=("src/project_pipeline/assurance/completion.py",),
    )
    assert decision.disposition is ScopeChangeDisposition.WITHIN_FROZEN_SCOPE
    assert decision.material is False


def test_new_behavior_requires_review_when_change_budget_remains():
    decision = evaluate_scope_change(scope(), requested_behavior=("new unrelated capability",))
    assert decision.disposition is ScopeChangeDisposition.REQUIRE_REVIEW
    assert decision.material is True


def test_scope_change_budget_exhaustion_blocks_autonomous_expansion():
    decision = evaluate_scope_change(
        scope(consumed_changes=2), requested_paths=("apps/new-ui/file.tsx",)
    )
    assert decision.disposition is ScopeChangeDisposition.CHANGE_BUDGET_EXHAUSTED


def test_retry_after_failure_requires_explicit_novelty_dimension():
    decision = evaluate_loop(
        (
            obs(1, failure="failure-a", output="a", action="a"),
            obs(2, failure="failure-b", output="b", action="b"),
        ),
        budget(),
    )
    assert decision.disposition is LoopDisposition.REQUIRE_NOVELTY
    assert any("novelty" in reason for reason in decision.reasons)
