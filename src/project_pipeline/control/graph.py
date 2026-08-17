from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime

import networkx as nx

from project_pipeline.domain.control import (
    BuildSequence,
    CriticalPathAnalysis,
    EligibilityState,
    ReadinessState,
    SequenceItem,
    SequenceScore,
    TaskControlFact,
    TaskEligibility,
    TaskReadiness,
    control_identifier,
)
from project_pipeline.domain.state import TaskLifecycleState


class ControlGraphError(ValueError):
    """Raised when accepted control inputs cannot form a valid work DAG."""


_TERMINAL = {TaskLifecycleState.DONE, TaskLifecycleState.CANCELLED}
_ACTIVE = {
    TaskLifecycleState.CLAIMED,
    TaskLifecycleState.IN_PROGRESS,
    TaskLifecycleState.IN_REVIEW,
    TaskLifecycleState.VALIDATING,
}


class BuildSequencer:
    """Deterministic dependency, readiness, critical-path, and priority analysis."""

    DEFAULT_DURATION_MINUTES = 60

    def __init__(self, facts: Iterable[TaskControlFact]) -> None:
        self.facts = tuple(sorted(facts, key=lambda item: item.task_id))
        self.by_id = {item.task_id: item for item in self.facts}
        if len(self.by_id) != len(self.facts):
            raise ControlGraphError("task control facts contain duplicate task identifiers")
        project_ids = {item.project_id for item in self.facts}
        if len(project_ids) > 1:
            raise ControlGraphError("one build sequence cannot mix multiple projects")
        self.project_id = next(iter(project_ids), "PROJECT-PIPELINE")
        self.graph = self._build_graph()

    def _build_graph(self) -> nx.DiGraph[str]:
        graph: nx.DiGraph[str] = nx.DiGraph()
        for fact in self.facts:
            graph.add_node(fact.task_id)
        for fact in self.facts:
            for dependency in fact.dependency_ids:
                if dependency not in self.by_id:
                    raise ControlGraphError(
                        f"task {fact.task_id} depends on unknown work item {dependency}"
                    )
                graph.add_edge(dependency, fact.task_id)
        if not nx.is_directed_acyclic_graph(graph):
            cycles = tuple(tuple(cycle) for cycle in nx.simple_cycles(graph))
            raise ControlGraphError(f"blocking dependency graph contains a cycle: {cycles[:3]}")
        return graph

    def graph_fingerprint(self) -> str:
        payload = {
            "nodes": [
                {
                    "task_id": item.task_id,
                    "state": item.state.value,
                    "issue_type": item.issue_type,
                    "priority": item.priority,
                    "risk": item.risk,
                    "dependencies": list(item.dependency_ids),
                    "blockers": list(item.blocker_ids),
                    "duration": item.expected_duration_minutes,
                    "deadline": item.deadline_utc.isoformat() if item.deadline_utc else None,
                    "accepted": item.accepted,
                    "policy_eligible": item.policy_eligible,
                    "approval_satisfied": item.approval_satisfied,
                    "context_satisfied": item.context_satisfied,
                    "resources_available": item.resources_available,
                    "environment_available": item.environment_available,
                    "human_required": item.human_required,
                    "external_blocked": item.external_blocked,
                    "reconciliation_required": item.reconciliation_required,
                }
                for item in self.facts
            ],
            "edges": sorted((source, target) for source, target in self.graph.edges()),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def eligibility(self, fact: TaskControlFact) -> TaskEligibility:
        reasons: list[str] = []
        if fact.issue_type == "EPIC":
            return TaskEligibility(
                task_id=fact.task_id,
                state=EligibilityState.POLICY_DENIED,
                eligible=False,
                reasons=("epic is a structural work container and is not directly executable",),
            )
        if fact.state in _TERMINAL:
            return TaskEligibility(
                task_id=fact.task_id,
                state=EligibilityState.TERMINAL,
                eligible=False,
                reasons=(f"task is terminal: {fact.state.value}",),
            )
        if fact.state in _ACTIVE:
            return TaskEligibility(
                task_id=fact.task_id,
                state=EligibilityState.ALREADY_ACTIVE,
                eligible=False,
                reasons=(f"task already has active execution state: {fact.state.value}",),
            )
        if fact.human_required:
            return TaskEligibility(
                task_id=fact.task_id,
                state=EligibilityState.HUMAN_REQUIRED,
                eligible=False,
                reasons=("task requires a human decision or action before autonomous admission",),
            )
        if fact.external_blocked:
            return TaskEligibility(
                task_id=fact.task_id,
                state=EligibilityState.EXTERNAL_BLOCKED,
                eligible=False,
                reasons=("task is blocked by an unavailable external dependency",),
            )
        if fact.reconciliation_required:
            return TaskEligibility(
                task_id=fact.task_id,
                state=EligibilityState.RECONCILIATION_REQUIRED,
                eligible=False,
                reasons=(
                    "all linked requirements are already implemented and evidenced; audit and batch-reconcile this item instead of opening a fresh implementation lane",
                ),
            )
        if not fact.accepted or not fact.policy_eligible:
            if not fact.accepted:
                reasons.append("task is not accepted into executable scope")
            if not fact.policy_eligible:
                reasons.append("task is denied by current policy eligibility")
            return TaskEligibility(
                task_id=fact.task_id,
                state=EligibilityState.POLICY_DENIED,
                eligible=False,
                reasons=tuple(reasons),
            )
        if fact.state in {TaskLifecycleState.BLOCKED, TaskLifecycleState.FAILED}:
            return TaskEligibility(
                task_id=fact.task_id,
                state=EligibilityState.BLOCKED,
                eligible=False,
                reasons=(
                    f"task state requires reconciliation before admission: {fact.state.value}",
                ),
            )
        return TaskEligibility(task_id=fact.task_id, state=EligibilityState.ELIGIBLE, eligible=True)

    def readiness(self, fact: TaskControlFact) -> TaskReadiness:
        eligibility = self.eligibility(fact)
        if eligibility.state is EligibilityState.TERMINAL:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.TERMINAL,
                ready=False,
                reasons=eligibility.reasons,
            )
        if eligibility.state is EligibilityState.ALREADY_ACTIVE:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.ACTIVE,
                ready=False,
                reasons=eligibility.reasons,
            )
        if not eligibility.eligible:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.BLOCKED
                if eligibility.state is EligibilityState.BLOCKED
                else ReadinessState.NOT_ELIGIBLE,
                ready=False,
                reasons=eligibility.reasons,
            )
        unresolved_dependencies = tuple(
            dependency
            for dependency in fact.dependency_ids
            if self.by_id[dependency].state is not TaskLifecycleState.DONE
        )
        unresolved_blockers = tuple(
            blocker
            for blocker in fact.blocker_ids
            if blocker in self.by_id and self.by_id[blocker].state is not TaskLifecycleState.DONE
        )
        if unresolved_dependencies:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.WAITING_DEPENDENCIES,
                ready=False,
                unresolved_dependencies=unresolved_dependencies,
                reasons=("one or more blocking dependencies are not done",),
            )
        if unresolved_blockers:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.BLOCKED,
                ready=False,
                unresolved_blockers=unresolved_blockers,
                reasons=("one or more explicit blockers remain unresolved",),
            )
        if fact.approval_required and not fact.approval_satisfied:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.WAITING_APPROVAL,
                ready=False,
                reasons=("required approval is not satisfied",),
            )
        if fact.context_required and not fact.context_satisfied:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.WAITING_CONTEXT,
                ready=False,
                reasons=("required execution context is not available",),
            )
        if not fact.resources_available:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.WAITING_RESOURCES,
                ready=False,
                reasons=("required resources are not available",),
            )
        if not fact.environment_available:
            return TaskReadiness(
                task_id=fact.task_id,
                state=ReadinessState.WAITING_ENVIRONMENT,
                ready=False,
                reasons=("required execution environment is not available",),
            )
        return TaskReadiness(task_id=fact.task_id, state=ReadinessState.READY, ready=True)

    def _durations(self) -> tuple[dict[str, int], str]:
        values: dict[str, int] = {}
        declared = 0
        remaining = 0
        for fact in self.facts:
            if fact.state in _TERMINAL or fact.issue_type == "EPIC":
                # Structural containers and terminal work do not consume execution duration.
                values[fact.task_id] = 0
            elif fact.expected_duration_minutes is None:
                remaining += 1
                values[fact.task_id] = self.DEFAULT_DURATION_MINUTES
            else:
                remaining += 1
                values[fact.task_id] = fact.expected_duration_minutes
                declared += 1
        if not values or remaining == 0:
            source = "EMPTY" if not values else "DEFAULT_HEURISTIC"
        elif declared == remaining:
            source = "DECLARED"
        elif declared == 0:
            source = "DEFAULT_HEURISTIC"
        else:
            source = "MIXED"
        return values, source

    def critical_path(self) -> CriticalPathAnalysis:
        if not self.facts:
            return CriticalPathAnalysis(
                path=(),
                total_duration_minutes=0,
                duration_source="EMPTY",
                earliest_finish_minutes={},
                slack_minutes={},
            )
        durations, duration_source = self._durations()
        earliest_finish: dict[str, int] = {}
        predecessor: dict[str, str | None] = {}
        topo = tuple(nx.lexicographical_topological_sort(self.graph, key=lambda value: value))
        for node in topo:
            preds = tuple(sorted(self.graph.predecessors(node)))
            if not preds:
                earliest_finish[node] = durations[node]
                predecessor[node] = None
            else:
                best = max(preds, key=lambda item: (earliest_finish[item], item))
                earliest_finish[node] = earliest_finish[best] + durations[node]
                predecessor[node] = best
        end = max(topo, key=lambda item: (earliest_finish[item], item))
        total = earliest_finish[end]
        path: list[str] = []
        cursor: str | None = end
        while cursor is not None:
            path.append(cursor)
            cursor = predecessor[cursor]
        path.reverse()

        latest_finish: dict[str, int] = {node: total for node in topo}
        for node in reversed(topo):
            succs = tuple(sorted(self.graph.successors(node)))
            if succs:
                latest_finish[node] = min(latest_finish[succ] - durations[succ] for succ in succs)
        slack = {node: max(0, latest_finish[node] - earliest_finish[node]) for node in topo}
        return CriticalPathAnalysis(
            path=tuple(path),
            total_duration_minutes=total,
            duration_source=duration_source,  # type: ignore[arg-type]
            earliest_finish_minutes=dict(sorted(earliest_finish.items())),
            slack_minutes=dict(sorted(slack.items())),
        )

    def _depths(self) -> dict[str, int]:
        depth: dict[str, int] = {}
        for node in nx.lexicographical_topological_sort(self.graph, key=lambda value: value):
            preds = tuple(self.graph.predecessors(node))
            depth[node] = 0 if not preds else 1 + max(depth[pred] for pred in preds)
        return depth

    def _deadline_score(self, deadline: datetime | None, now: datetime) -> int:
        if deadline is None:
            return 0
        hours = (deadline - now).total_seconds() / 3600
        if hours <= 0:
            return 200
        if hours <= 24:
            return 150
        if hours <= 72:
            return 100
        if hours <= 168:
            return 50
        return 0

    def _score(
        self,
        fact: TaskControlFact,
        *,
        critical_path: set[str],
        downstream_count: int,
        now: datetime,
    ) -> SequenceScore:
        priority = {"P0": 1000, "P1": 700, "P2": 400, "P3": 100}[fact.priority]
        critical = 200 if fact.task_id in critical_path else 0
        deadline = self._deadline_score(fact.deadline_utc, now)
        risk = {"LOW": 0, "MEDIUM": 10, "HIGH": 25, "CRITICAL": 40}[fact.risk]
        unblock = min(150, downstream_count * 10)
        duration = 0
        if fact.expected_duration_minutes is not None:
            duration = max(-80, -int(fact.expected_duration_minutes / 60) * 2)
        total = priority + critical + deadline + risk + unblock + duration
        return SequenceScore(
            task_id=fact.task_id,
            priority_score=priority,
            critical_path_score=critical,
            deadline_score=deadline,
            risk_score=risk,
            unblock_score=unblock,
            duration_score=duration,
            total_score=total,
        )

    def build_sequence(self, *, now: datetime | None = None) -> BuildSequence:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        critical = self.critical_path()
        critical_nodes = {
            node
            for node, slack in critical.slack_minutes.items()
            if slack == 0 and self.by_id[node].state not in _TERMINAL
        }
        depths = self._depths()
        readiness = {fact.task_id: self.readiness(fact) for fact in self.facts}
        active = sum(item.state is ReadinessState.ACTIVE for item in readiness.values())
        blocked_states = {
            ReadinessState.BLOCKED,
            ReadinessState.WAITING_APPROVAL,
            ReadinessState.WAITING_CONTEXT,
            ReadinessState.WAITING_DEPENDENCIES,
            ReadinessState.WAITING_ENVIRONMENT,
            ReadinessState.WAITING_RESOURCES,
            ReadinessState.NOT_ELIGIBLE,
        }
        blocked = sum(
            item.state in blocked_states and self.by_id[task_id].issue_type != "EPIC"
            for task_id, item in readiness.items()
        )
        candidates: list[tuple[TaskControlFact, SequenceScore, int]] = []
        for fact in self.facts:
            if not readiness[fact.task_id].ready:
                continue
            downstream = len(nx.descendants(self.graph, fact.task_id))
            score = self._score(
                fact,
                critical_path=critical_nodes,
                downstream_count=downstream,
                now=now,
            )
            candidates.append((fact, score, downstream))
        candidates.sort(key=lambda item: (-item[1].total_score, item[0].task_id))
        items = tuple(
            SequenceItem(
                rank=index,
                task_id=fact.task_id,
                readiness=ReadinessState.READY,
                score=score,
                dependency_depth=depths[fact.task_id],
                downstream_count=downstream,
                on_critical_path=fact.task_id in critical_nodes,
            )
            for index, (fact, score, downstream) in enumerate(candidates, start=1)
        )
        fingerprint = self.graph_fingerprint()
        sequence_id = control_identifier(
            "SEQ", self.project_id, fingerprint, *(item.task_id for item in items)
        )
        return BuildSequence(
            sequence_id=sequence_id,
            project_id=self.project_id,
            graph_fingerprint=fingerprint,
            task_count=len(self.facts),
            edge_count=self.graph.number_of_edges(),
            ready_count=len(items),
            active_count=active,
            blocked_count=blocked,
            critical_path=critical,
            ordered_ready_work=items,
            generated_at_utc=now,
        )
