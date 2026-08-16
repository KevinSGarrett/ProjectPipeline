from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from project_pipeline.control.graph import BuildSequencer, ControlGraphError
from project_pipeline.domain import ImplementationState, RequirementDisposition
from project_pipeline.domain.control import (
    BuildSequence,
    CompletionProjection,
    CompletionProjectionState,
    ControlSnapshot,
    ScopeFinding,
    ScopeFindingKind,
    ScopeReconciliationReport,
    TaskControlFact,
    TaskReadiness,
    control_identifier,
)
from project_pipeline.domain.state import TaskLifecycleState
from project_pipeline.jira import load_issues
from project_pipeline.persistence import SQLiteStateStore
from project_pipeline.requirements import load_requirement_catalog

_COMPLETE_REQUIREMENT_STATES = {
    ImplementationState.IMPLEMENTED.value,
    ImplementationState.MOCK_VERIFIED.value,
    ImplementationState.LIVE_VERIFIED.value,
    ImplementationState.BLOCKED_EXTERNAL.value,
}
_TERMINAL_WORK = {TaskLifecycleState.DONE, TaskLifecycleState.CANCELLED}
_ACTIVE_WORK = {
    TaskLifecycleState.CLAIMED,
    TaskLifecycleState.IN_PROGRESS,
    TaskLifecycleState.IN_REVIEW,
    TaskLifecycleState.VALIDATING,
}
_RECONCILABLE_ISSUE_IMPLEMENTATION_STATES = {
    ImplementationState.IMPLEMENTED.value,
    ImplementationState.MOCK_VERIFIED.value,
    ImplementationState.LIVE_VERIFIED.value,
}


def issue_has_reconciliation_evidence(root: Path, issue: dict[str, Any]) -> bool:
    implementation_state = issue.get("implementation_state")
    if implementation_state not in _RECONCILABLE_ISSUE_IMPLEMENTATION_STATES | {
        ImplementationState.PLANNED_ONLY.value,
        ImplementationState.PARTIALLY_IMPLEMENTED.value,
    }:
        return False
    artifacts = issue.get("expected_implementation_artifacts", ())
    if not artifacts or not all(
        isinstance(path, str) and (root / path).exists() for path in artifacts
    ):
        return False
    criteria = issue.get("acceptance_criteria", ())
    if not criteria:
        return False
    for item in criteria:
        if not isinstance(item, dict) or not isinstance(item.get("verification"), dict):
            return False
        verification = item["verification"]
        path = verification.get("path")
        if not isinstance(path, str) or not (root / path).exists():
            return False
        if (
            implementation_state in _RECONCILABLE_ISSUE_IMPLEMENTATION_STATES
            and verification.get("status") != "VERIFIED"
        ):
            return False
    return bool(issue.get("required_tests")) and bool(issue.get("completion_evidence"))


def _json_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProjectControlKernel:
    """Deterministic project-control projection over accepted repository state."""

    def __init__(self, root: Path, store: SQLiteStateStore, project_id: str) -> None:
        self.root = root.resolve()
        self.store = store
        self.project_id = project_id

    def task_facts(self) -> tuple[TaskControlFact, ...]:
        issues = {item["local_id"]: item for item in load_issues(self.root)}
        requirements = {
            item["requirement_id"]: item for item in load_requirement_catalog(self.root)
        }
        states = self.store.list_task_states(self.project_id)
        facts: list[TaskControlFact] = []
        for state in states:
            issue = issues.get(state.task_id)
            if issue is None:
                continue
            linked = [
                requirements[item]
                for item in issue.get("requirement_ids", [])
                if item in requirements
            ]
            accepted = all(
                item.get("disposition") == RequirementDisposition.ACCEPTED.value for item in linked
            )
            external_blocked = bool(linked) and all(
                item.get("implementation_state") == ImplementationState.BLOCKED_EXTERNAL.value
                for item in linked
            )
            implementation_complete = bool(linked) and all(
                item.get("implementation_state") in _COMPLETE_REQUIREMENT_STATES for item in linked
            )
            implementation_mapped = implementation_complete and all(
                item.get("implementation_state") == ImplementationState.BLOCKED_EXTERNAL.value
                or (
                    bool(item.get("implementation_paths"))
                    and all((self.root / path).exists() for path in item["implementation_paths"])
                    and bool(item.get("evidence_ids"))
                )
                for item in linked
            )
            priority = state.priority
            facts.append(
                TaskControlFact(
                    task_id=state.task_id,
                    project_id=self.project_id,
                    state=state.state,
                    issue_type=issue.get("issue_type", "TASK"),
                    priority=priority,
                    risk=issue.get("risk_classification", "MEDIUM"),
                    dependency_ids=state.dependency_ids,
                    blocker_ids=state.blocker_ids,
                    requirement_ids=tuple(issue.get("requirement_ids", ())),
                    accepted=accepted,
                    external_blocked=external_blocked,
                    reconciliation_required=implementation_mapped
                    and issue_has_reconciliation_evidence(self.root, issue),
                )
            )
        return tuple(sorted(facts, key=lambda item: item.task_id))

    def scope_reconciliation(self) -> ScopeReconciliationReport:
        requirements = load_requirement_catalog(self.root)
        issues = load_issues(self.root)
        req_by_id = {item["requirement_id"]: item for item in requirements}
        issue_ids = {item["local_id"] for item in issues}
        findings: list[ScopeFinding] = []

        for requirement in requirements:
            if requirement.get("disposition") != RequirementDisposition.ACCEPTED.value:
                continue
            jira_ids = tuple(requirement.get("jira_ids", ()))
            if not jira_ids:
                findings.append(
                    ScopeFinding(
                        kind=ScopeFindingKind.REQUIREMENT_WITHOUT_WORK,
                        subject_id=requirement["requirement_id"],
                        detail="Accepted requirement has no mapped work item.",
                    )
                )
            if requirement.get(
                "implementation_state"
            ) in _COMPLETE_REQUIREMENT_STATES and not requirement.get("implementation_paths"):
                findings.append(
                    ScopeFinding(
                        kind=ScopeFindingKind.IMPLEMENTED_REQUIREMENT_WITHOUT_ARTIFACT,
                        subject_id=requirement["requirement_id"],
                        detail="Requirement is represented as implemented or externally blocked without an implementation artifact mapping.",
                    )
                )

        for issue in issues:
            requirement_ids = tuple(issue.get("requirement_ids", ()))
            if not requirement_ids and issue.get("issue_type") not in {"EPIC"}:
                findings.append(
                    ScopeFinding(
                        kind=ScopeFindingKind.WORK_WITHOUT_REQUIREMENT,
                        subject_id=issue["local_id"],
                        detail="Work item has no requirement mapping.",
                    )
                )
            for requirement_id in requirement_ids:
                if requirement_id not in req_by_id:
                    findings.append(
                        ScopeFinding(
                            kind=ScopeFindingKind.UNKNOWN_REQUIREMENT,
                            subject_id=issue["local_id"],
                            related_id=requirement_id,
                            detail="Work item references a requirement absent from the authoritative registry.",
                        )
                    )
            relations = set(issue.get("dependencies", ())) | set(issue.get("blockers", ()))
            relations.update(
                relation.get("target")
                for relation in issue.get("relationships", ())
                if relation.get("type") in {"DEPENDS_ON", "BLOCKED_BY", "IS_BLOCKED_BY"}
            )
            for related in sorted(item for item in relations if item):
                if related not in issue_ids:
                    findings.append(
                        ScopeFinding(
                            kind=ScopeFindingKind.UNKNOWN_DEPENDENCY,
                            subject_id=issue["local_id"],
                            related_id=related,
                            detail="Work item references a dependency or blocker absent from the local Jira authority.",
                        )
                    )
            if issue.get("state") == "DONE" and not issue.get("completion_evidence"):
                findings.append(
                    ScopeFinding(
                        kind=ScopeFindingKind.DONE_WITHOUT_EVIDENCE,
                        subject_id=issue["local_id"],
                        detail="Done work item has no completion evidence mapping.",
                    )
                )
            if (
                issue.get("state") == "DONE"
                and issue.get("implementation_state") == ImplementationState.PLANNED_ONLY.value
            ):
                findings.append(
                    ScopeFinding(
                        kind=ScopeFindingKind.DONE_WITHOUT_IMPLEMENTATION,
                        subject_id=issue["local_id"],
                        detail="Done work item is still represented as planned only.",
                    )
                )

        findings.sort(key=lambda item: (item.kind.value, item.subject_id, item.related_id or ""))
        payload = [item.model_dump(mode="json") for item in findings]
        fingerprint = _json_fingerprint(payload)
        return ScopeReconciliationReport(
            report_id=control_identifier("SCOPE", self.project_id, fingerprint),
            project_id=self.project_id,
            requirement_count=len(requirements),
            work_item_count=len(issues),
            findings=tuple(findings),
            fingerprint=fingerprint,
        )

    def completion_projection(
        self, sequence: BuildSequence, readiness: tuple[TaskReadiness, ...]
    ) -> CompletionProjection:
        requirements = [
            item
            for item in load_requirement_catalog(self.root)
            if item.get("disposition") == RequirementDisposition.ACCEPTED.value
        ]
        states = self.store.list_task_states(self.project_id)
        total = len(states)
        completed = sum(item.state in _TERMINAL_WORK for item in states)
        active = sum(item.state in _ACTIVE_WORK for item in states)
        blocked = sum(item.state is TaskLifecycleState.BLOCKED for item in states)
        failed = sum(item.state is TaskLifecycleState.FAILED for item in states)
        req_complete = sum(
            item.get("implementation_state") in _COMPLETE_REQUIREMENT_STATES
            for item in requirements
        )
        reasons: list[str] = []
        all_work_terminal = completed == total
        all_requirements_complete = req_complete == len(requirements)
        if failed:
            state = CompletionProjectionState.FAILED
            reasons.append(f"{failed} work items are in FAILED state")
        elif blocked and sequence.ready_count == 0 and active == 0:
            state = CompletionProjectionState.BLOCKED
            reasons.append("no independent ready or active work remains while blocked work exists")
        elif all_work_terminal and all_requirements_complete:
            state = CompletionProjectionState.READY_FOR_COMPLETION_GATE
            reasons.append(
                "all accepted requirements and work items satisfy the control-plane projection"
            )
            reasons.append("independent Completion Gate evaluation is still required")
        else:
            state = CompletionProjectionState.INCOMPLETE
            if not all_work_terminal:
                reasons.append(f"{total - completed} work items are not terminal")
            if not all_requirements_complete:
                reasons.append(
                    f"{len(requirements) - req_complete} accepted requirements are not implemented or externally blocked"
                )
            if sequence.ready_count:
                reasons.append(
                    f"{sequence.ready_count} independent work items are ready to continue"
                )
        return CompletionProjection(
            projection_id=control_identifier(
                "COMPLETE",
                self.project_id,
                str(total),
                str(completed),
                str(req_complete),
                state.value,
            ),
            project_id=self.project_id,
            state=state,
            total_work_items=total,
            completed_work_items=completed,
            active_work_items=active,
            blocked_work_items=blocked,
            failed_work_items=failed,
            accepted_requirements=len(requirements),
            implemented_or_external_blocked_requirements=req_complete,
            ready_work_items=sequence.ready_count,
            verification_eligible=state is CompletionProjectionState.READY_FOR_COMPLETION_GATE,
            final_completion_gate_satisfied=False,
            reasons=tuple(reasons),
        )

    def evaluate(self) -> ControlSnapshot:
        facts = self.task_facts()
        sequencer = BuildSequencer(facts)
        sequence = sequencer.build_sequence()
        eligibility = tuple(sequencer.eligibility(item) for item in facts)
        readiness = tuple(sequencer.readiness(item) for item in facts)
        scope = self.scope_reconciliation()
        completion = self.completion_projection(sequence, readiness)
        # Semantic identity intentionally excludes generated timestamps so repeated
        # evaluation of unchanged accepted state produces the same snapshot ID.
        fingerprint = _json_fingerprint(
            {
                "sequence_id": sequence.sequence_id,
                "graph_fingerprint": sequence.graph_fingerprint,
                "scope_report_id": scope.report_id,
                "completion_projection_id": completion.projection_id,
                "eligibility": [item.model_dump(mode="json") for item in eligibility],
                "readiness": [item.model_dump(mode="json") for item in readiness],
            }
        )
        return ControlSnapshot(
            snapshot_id=control_identifier("CTRL", self.project_id, fingerprint),
            project_id=self.project_id,
            sequence=sequence,
            scope=scope,
            completion=completion,
            eligibility=eligibility,
            readiness=readiness,
            snapshot_fingerprint=fingerprint,
        )

    def readiness_transition_plan(
        self, *, task_ids: frozenset[str] | None = None
    ) -> tuple[dict[str, Any], ...]:
        snapshot = self.evaluate()
        ready = {item.task_id for item in snapshot.readiness if item.ready}
        states = {item.task_id: item for item in self.store.list_task_states(self.project_id)}
        if task_ids is not None:
            unknown = task_ids - states.keys()
            if unknown:
                raise ValueError(
                    "unknown task IDs in readiness transition request: "
                    + ", ".join(sorted(unknown))
                )
            ready &= task_ids
        operations: list[dict[str, Any]] = []
        for task_id in sorted(ready):
            state = states[task_id]
            if state.state is TaskLifecycleState.BACKLOG:
                operations.append(
                    {
                        "task_id": task_id,
                        "previous_state": state.state.value,
                        "next_state": TaskLifecycleState.READY.value,
                        "expected_version": state.version,
                        "reason": "Control Kernel recomputed all deterministic readiness predicates as satisfied.",
                    }
                )
        return tuple(operations)

    def apply_readiness_transitions(
        self,
        *,
        actor_id: str,
        correlation_id: str,
        task_ids: frozenset[str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        operations = self.readiness_transition_plan(task_ids=task_ids)
        results: list[dict[str, Any]] = []
        for operation in operations:
            state = self.store.transition_task(
                task_id=operation["task_id"],
                next_state=TaskLifecycleState.READY,
                expected_version=operation["expected_version"],
                reason=operation["reason"],
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            results.append(state.model_dump(mode="json"))
        return tuple(results)


__all__ = ["ControlGraphError", "ProjectControlKernel"]
