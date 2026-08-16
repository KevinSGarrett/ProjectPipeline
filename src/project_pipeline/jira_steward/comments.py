from __future__ import annotations

from project_pipeline.domain.jira import (
    JiraCommentIntent,
    JiraLifecycleState,
    JiraTransitionReadiness,
    LocalJiraIssue,
)

_ALLOWED_TRANSITIONS: dict[JiraLifecycleState, frozenset[JiraLifecycleState]] = {
    JiraLifecycleState.DISCOVERED: frozenset(
        {JiraLifecycleState.BACKLOG, JiraLifecycleState.DEFERRED, JiraLifecycleState.CANCELLED}
    ),
    JiraLifecycleState.BACKLOG: frozenset(
        {
            JiraLifecycleState.READY,
            JiraLifecycleState.BLOCKED,
            JiraLifecycleState.DEFERRED,
            JiraLifecycleState.CANCELLED,
        }
    ),
    JiraLifecycleState.READY: frozenset(
        {
            JiraLifecycleState.IN_PROGRESS,
            JiraLifecycleState.BLOCKED,
            JiraLifecycleState.DEFERRED,
            JiraLifecycleState.CANCELLED,
        }
    ),
    JiraLifecycleState.IN_PROGRESS: frozenset(
        {
            JiraLifecycleState.REVIEW,
            JiraLifecycleState.BLOCKED,
            JiraLifecycleState.FAILED,
            JiraLifecycleState.CANCELLED,
        }
    ),
    JiraLifecycleState.REVIEW: frozenset(
        {JiraLifecycleState.IN_PROGRESS, JiraLifecycleState.VALIDATION, JiraLifecycleState.BLOCKED}
    ),
    JiraLifecycleState.VALIDATION: frozenset(
        {
            JiraLifecycleState.IN_PROGRESS,
            JiraLifecycleState.REVIEW,
            JiraLifecycleState.MERGE_READY,
            JiraLifecycleState.DONE,
            JiraLifecycleState.BLOCKED,
            JiraLifecycleState.FAILED,
        }
    ),
    JiraLifecycleState.MERGE_READY: frozenset(
        {JiraLifecycleState.VALIDATION, JiraLifecycleState.DONE, JiraLifecycleState.BLOCKED}
    ),
    JiraLifecycleState.BLOCKED: frozenset(
        {
            JiraLifecycleState.BACKLOG,
            JiraLifecycleState.READY,
            JiraLifecycleState.IN_PROGRESS,
            JiraLifecycleState.REVIEW,
            JiraLifecycleState.VALIDATION,
            JiraLifecycleState.CANCELLED,
        }
    ),
    JiraLifecycleState.FAILED: frozenset(
        {JiraLifecycleState.READY, JiraLifecycleState.IN_PROGRESS, JiraLifecycleState.CANCELLED}
    ),
    JiraLifecycleState.DEFERRED: frozenset(
        {JiraLifecycleState.BACKLOG, JiraLifecycleState.CANCELLED}
    ),
    JiraLifecycleState.CANCELLED: frozenset({JiraLifecycleState.BACKLOG}),
    JiraLifecycleState.DONE: frozenset({JiraLifecycleState.IN_PROGRESS}),
}


def validate_comment_intent(
    intent: JiraCommentIntent,
    *,
    existing_fingerprints: frozenset[str] = frozenset(),
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if intent.semantic_fingerprint() in existing_fingerprints:
        reasons.append("A semantically equivalent Jira comment already exists.")
    if intent.kind.value.endswith("EVIDENCE") and not intent.evidence_references:
        reasons.append("Evidence comments require at least one evidence reference.")
    if intent.kind.value == "COMPLETION_SUMMARY" and not intent.evidence_references:
        reasons.append("Completion comments require completion evidence references.")
    return not reasons, tuple(reasons)


def evaluate_transition(
    issue: LocalJiraIssue,
    to_state: JiraLifecycleState,
    *,
    assigned: bool,
    branch_present: bool,
    implementation_evidence_present: bool,
    required_tests_passed: bool,
    acceptance_criteria_verified: bool,
    independent_review_complete: bool,
    blockers_clear: bool,
    completion_evidence_present: bool,
) -> JiraTransitionReadiness:
    reasons: list[str] = []
    allowed_targets = _ALLOWED_TRANSITIONS[issue.state]
    if to_state not in allowed_targets:
        reasons.append(f"Transition {issue.state.value} -> {to_state.value} is not legal.")
    if (
        to_state
        in {
            JiraLifecycleState.IN_PROGRESS,
            JiraLifecycleState.REVIEW,
            JiraLifecycleState.VALIDATION,
            JiraLifecycleState.MERGE_READY,
            JiraLifecycleState.DONE,
        }
        and not assigned
    ):
        reasons.append(
            "The work item must be assigned before entering active or completion states."
        )
    if to_state in {
        JiraLifecycleState.REVIEW,
        JiraLifecycleState.VALIDATION,
        JiraLifecycleState.MERGE_READY,
        JiraLifecycleState.DONE,
    }:
        if not implementation_evidence_present:
            reasons.append("Implementation evidence is required before review or completion.")
        if not branch_present:
            reasons.append("A governed branch or equivalent workspace must exist before review.")
        if not required_tests_passed:
            reasons.append("Required tests must pass before review or completion.")
    if to_state in {JiraLifecycleState.MERGE_READY, JiraLifecycleState.DONE}:
        if not acceptance_criteria_verified:
            reasons.append("Acceptance criteria must be verified before merge-ready or done.")
        if not independent_review_complete:
            reasons.append("Required independent review must be complete.")
        if not blockers_clear:
            reasons.append("Unresolved blockers prevent merge-ready or done.")
        if not completion_evidence_present:
            reasons.append("Completion evidence is required before merge-ready or done.")
    return JiraTransitionReadiness(
        local_id=issue.local_id,
        from_state=issue.state,
        to_state=to_state,
        assigned=assigned,
        implementation_evidence_present=implementation_evidence_present,
        branch_present=branch_present,
        required_tests_passed=required_tests_passed,
        acceptance_criteria_verified=acceptance_criteria_verified,
        independent_review_complete=independent_review_complete,
        blockers_clear=blockers_clear,
        completion_evidence_present=completion_evidence_present,
        allowed=not reasons,
        reasons=tuple(reasons),
    )
