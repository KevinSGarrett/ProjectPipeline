from __future__ import annotations

from collections.abc import Iterable

from project_pipeline.domain.control import (
    ControlCohortCounts,
    EligibilityState,
    ReadinessState,
    TaskControlFact,
    TaskEligibility,
    TaskReadiness,
)
from project_pipeline.domain.state import TaskLifecycleState

_TERMINAL = {TaskLifecycleState.DONE, TaskLifecycleState.CANCELLED}
_STRUCTURAL_TYPES = {"EPIC"}


def is_structural_container(fact: TaskControlFact) -> bool:
    return fact.issue_type in _STRUCTURAL_TYPES


def summarize_control_cohorts(
    facts: Iterable[TaskControlFact],
    eligibility: Iterable[TaskEligibility],
    readiness: Iterable[TaskReadiness],
) -> ControlCohortCounts:
    fact_list = tuple(facts)
    eligibility_list = tuple(eligibility)
    readiness_list = tuple(readiness)
    reconciliation = [
        item for item in fact_list if item.reconciliation_required and item.state not in _TERMINAL
    ]
    structural = [item for item in reconciliation if is_structural_container(item)]
    eligibility_states = [item.state for item in eligibility_list]
    return ControlCohortCounts(
        total_work_items=len(fact_list),
        reconciliation_facts=len(reconciliation),
        structural_container_facts=len(structural),
        leaf_reconciliation_facts=len(reconciliation) - len(structural),
        eligibility_reconciliation=sum(
            state is EligibilityState.RECONCILIATION_REQUIRED for state in eligibility_states
        ),
        eligibility_eligible=sum(
            state is EligibilityState.ELIGIBLE for state in eligibility_states
        ),
        eligibility_policy_denied=sum(
            state is EligibilityState.POLICY_DENIED for state in eligibility_states
        ),
        eligibility_product_scope_paused=sum(
            state is EligibilityState.PRODUCT_SCOPE_PAUSED for state in eligibility_states
        ),
        eligibility_terminal=sum(
            state is EligibilityState.TERMINAL for state in eligibility_states
        ),
        eligibility_already_active=sum(
            state is EligibilityState.ALREADY_ACTIVE for state in eligibility_states
        ),
        eligibility_blocked=sum(state is EligibilityState.BLOCKED for state in eligibility_states),
        eligibility_blocked_external=sum(
            state is EligibilityState.BLOCKED_EXTERNAL for state in eligibility_states
        ),
        dependency_ready=sum(item.state is ReadinessState.READY for item in readiness_list),
    )


def describe_reconciliation_cohorts(cohorts: ControlCohortCounts) -> str:
    return (
        f"{cohorts.reconciliation_facts} reconciliation-class facts "
        f"({cohorts.leaf_reconciliation_facts} RECONCILIATION_REQUIRED leaves are "
        "directly reconcilable; "
        f"{cohorts.structural_container_facts} structural container projections "
        "are not independently executable)"
    )


def assert_cohort_invariants(
    facts: Iterable[TaskControlFact],
    eligibility: Iterable[TaskEligibility],
    readiness: Iterable[TaskReadiness],
    cohorts: ControlCohortCounts,
) -> None:
    recomputed = summarize_control_cohorts(facts, eligibility, readiness)
    if recomputed != cohorts:
        raise ValueError("control cohort counts drifted from the same-snapshot facts")
    if cohorts.reconciliation_facts != (
        cohorts.leaf_reconciliation_facts + cohorts.structural_container_facts
    ):
        raise ValueError("reconciliation facts must equal leaf plus structural container counts")
    if cohorts.eligibility_reconciliation > cohorts.reconciliation_facts:
        raise ValueError("eligibility reconciliation cannot exceed reconciliation-class facts")
    if cohorts.dependency_ready > cohorts.eligibility_eligible:
        raise ValueError("dependency-ready items cannot exceed eligible items")
