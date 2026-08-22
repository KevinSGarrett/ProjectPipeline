from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from project_pipeline.command_center.models import CommandCenterSnapshot
from project_pipeline.contracts.envelopes import ContractModel
from project_pipeline.control.cohorts import describe_reconciliation_cohorts
from project_pipeline.domain.control import ControlCohortCounts


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationGraphNode(ContractModel):
    node_id: str = Field(min_length=1, max_length=191)
    kind: Literal["requirement", "jira", "evidence", "component"]
    label: str = Field(min_length=1, max_length=500)
    state: str = Field(min_length=1, max_length=100)
    authoritative_path: str | None = Field(default=None, max_length=600)


class ApplicationGraphEdge(ContractModel):
    source: str = Field(min_length=1, max_length=191)
    target: str = Field(min_length=1, max_length=191)
    kind: str = Field(min_length=1, max_length=100)


class ApplicationGraph(ContractModel):
    nodes: tuple[ApplicationGraphNode, ...] = ()
    edges: tuple[ApplicationGraphEdge, ...] = ()
    truncated: bool = False


class ApplicationEvidenceRecord(ContractModel):
    evidence_id: str = Field(min_length=1, max_length=191)
    kind: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1000)
    path: str | None = Field(default=None, max_length=600)


class ApplicationSyncStatus(ContractModel):
    system: Literal["Jira", "GitHub"]
    mode: str = Field(min_length=1, max_length=100)
    remote_mutation_performed: bool = False
    stale: bool = True
    local_record_count: int = Field(default=0, ge=0)
    pending_outbox_count: int = Field(default=0, ge=0)
    conflict_count: int = Field(default=0, ge=0)
    note: str = Field(min_length=1, max_length=1000)


class ApplicationWorkItem(ContractModel):
    work_id: str = Field(min_length=1, max_length=191)
    title: str = Field(min_length=1, max_length=500)
    state: str = Field(min_length=1, max_length=100)
    owner: str | None = Field(default=None, max_length=191)
    worker: str | None = Field(default=None, max_length=191)
    workspace: str | None = Field(default=None, max_length=512)
    stage: str | None = Field(default=None, max_length=191)
    resource_lease_id: str | None = Field(default=None, max_length=191)
    last_progress_at_utc: datetime | None = None
    next_transition: str | None = Field(default=None, max_length=500)
    critical_path: bool = False


class CommandCenterApplicationProjection(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str = Field(min_length=3, max_length=191)
    canonical_authority: Literal["PROJECT_PIPELINE"] = "PROJECT_PIPELINE"
    ui_state_authoritative: Literal[False] = False
    readiness: dict[str, float] = Field(default_factory=dict)
    graph: ApplicationGraph = Field(default_factory=ApplicationGraph)
    live_work: tuple[ApplicationWorkItem, ...] = ()
    evidence: tuple[ApplicationEvidenceRecord, ...] = ()
    synchronization: tuple[ApplicationSyncStatus, ...] = ()
    approvals_detail_available: bool = False
    approvals_detail: tuple[dict[str, Any], ...] = ()
    decisions_detail: tuple[dict[str, Any], ...] = ()
    recovery_detail: tuple[dict[str, Any], ...] = ()
    budget_detail: dict[str, Any] = Field(default_factory=dict)
    provider_detail: dict[str, Any] = Field(default_factory=dict)
    context_detail: dict[str, Any] = Field(default_factory=dict)
    generated_at_utc: datetime = Field(default_factory=utc_now)


def _workspace_for_issue(item: dict[str, Any]) -> str:
    locations = [str(path) for path in (item.get("expected_file_locations") or []) if str(path)]
    if locations:
        return locations[0][:512]
    return f"repository:{item.get('local_id', 'UNKNOWN')}"


def _lease_id_for_issue(item: dict[str, Any]) -> str | None:
    observation = item.get("last_remote_observation")
    if isinstance(observation, dict) and observation.get("lease_id"):
        return str(observation["lease_id"])[:191]
    labels = [str(label) for label in (item.get("labels") or [])]
    for label in labels:
        if label.startswith("lease:"):
            return label.split(":", 1)[1][:191]
    local_id = str(item.get("local_id") or "")
    return f"repo-claim:{local_id}" if local_id else None


def _observation_time(item: dict[str, Any]) -> datetime | None:
    observation = item.get("last_remote_observation")
    raw = None
    if isinstance(observation, dict):
        raw = observation.get("observed_at_utc")
    raw = raw or item.get("updated_at_utc")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


class RepositoryApplicationProjectionBuilder:
    """Build a non-authoritative UI projection from repository-local canonical registries.

    The builder never invents remote state. Live approval/recovery detail can be supplied by a
    runtime-specific provider; repository projection only exposes facts present in the snapshot
    and committed registries.
    """

    def __init__(self, root: Path, *, max_graph_nodes: int = 160, max_evidence: int = 80) -> None:
        self.root = root.resolve()
        self.max_graph_nodes = max_graph_nodes
        self.max_evidence = max_evidence

    def build(self, snapshot: CommandCenterSnapshot) -> CommandCenterApplicationProjection:
        requirements = _read_jsonl(self.root / "plans/_traceability/requirements.jsonl")
        issues = _read_jsonl(self.root / "jira/indexes/issues.jsonl")
        evidence = _read_jsonl(self.root / "evidence/EVIDENCE_LEDGER.jsonl")

        readiness = {item.metric_id: round(item.value * 100, 2) for item in snapshot.readiness}
        graph = self._graph(requirements, issues, evidence)
        live_work = tuple(
            ApplicationWorkItem(
                work_id=str(item.get("local_id", "UNKNOWN")),
                title=str(item.get("title", "Untitled work")),
                state=str(item.get("state", "UNKNOWN")),
                owner=(
                    str(item["owner_required_capability"])
                    if item.get("owner_required_capability")
                    else None
                ),
                worker=(
                    str(item["owner_required_capability"])
                    if item.get("owner_required_capability")
                    else "repository"
                ),
                workspace=_workspace_for_issue(item),
                stage=str(item.get("implementation_state", "UNKNOWN")),
                resource_lease_id=_lease_id_for_issue(item),
                last_progress_at_utc=_observation_time(item),
                next_transition=self._next_transition(item),
                critical_path=bool("critical-path" in (item.get("labels") or [])),
            )
            for item in issues
            if item.get("state") == "IN_PROGRESS"
        )[:60]
        evidence_rows = tuple(self._evidence_row(row) for row in evidence[-self.max_evidence :])
        sync = (self._jira_sync_status(len(issues)), self._github_sync_status())
        complete = {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED", "BLOCKED_EXTERNAL"}
        incomplete_requirement_count = sum(
            1
            for row in requirements
            if row.get("disposition") == "ACCEPTED"
            and row.get("implementation_state") not in complete
        )
        implemented_not_done = sum(
            1
            for item in issues
            if item.get("implementation_state") == "IMPLEMENTED" and item.get("state") != "DONE"
        )
        context_detail = dict(snapshot.context_summary)
        control_cohorts = context_detail.get("control_cohorts")
        reconciliation_sentence = None
        if isinstance(control_cohorts, dict):
            cohorts = ControlCohortCounts.model_validate(control_cohorts)
            reconciliation_sentence = describe_reconciliation_cohorts(cohorts)
        context_detail.update(
            {
                "incomplete_requirement_count": incomplete_requirement_count,
                "implemented_not_done_issue_count": implemented_not_done,
                "reconciliation_is_immediately_batchable": False,
                "structural_containers_are_not_independently_executable": True,
                "ready_count_is_not_a_stop_signal": True,
                "reconciliation_sentence": reconciliation_sentence,
                "next_autonomous_work": (
                    "batch-reconcile evidence-backed leaf work, then implement "
                    "the highest-impact remaining incomplete Completion Gate domain"
                ),
                "user_action_required": False,
            }
        )
        return CommandCenterApplicationProjection(
            project_id=snapshot.project_id,
            readiness=readiness,
            graph=graph,
            live_work=live_work,
            evidence=evidence_rows,
            synchronization=sync,
            approvals_detail_available=False,
            approvals_detail=(),
            decisions_detail=(),
            recovery_detail=tuple(
                {"incident_id": value, "detail_state": "LIVE_PROVIDER_REQUIRED"}
                for value in snapshot.active_incident_ids
            ),
            budget_detail=dict(snapshot.budget_summary),
            provider_detail=dict(snapshot.provider_summary),
            context_detail=context_detail,
        )

    def _count_jsonl(self, relative: str) -> int:
        return len(_read_jsonl(self.root / relative))

    def _read_json(self, relative: str) -> dict[str, Any] | None:
        path = self.root / relative
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _jira_sync_status(self, local_issue_count: int) -> ApplicationSyncStatus:
        guard = self._read_json("jira/reports/jira_sync_guard.json")
        snapshot = self._read_json("jira/reports/live_status_snapshot.json")
        pending = self._count_jsonl("jira/reports/outbox.jsonl")
        conflicts = self._count_jsonl("jira/reports/conflicts.jsonl")
        if not isinstance(guard, dict) or not isinstance(snapshot, dict):
            return ApplicationSyncStatus(
                system="Jira",
                mode="LOCAL_ONLY",
                remote_mutation_performed=False,
                stale=True,
                local_record_count=local_issue_count,
                pending_outbox_count=pending,
                conflict_count=conflicts,
                note="Repository-local Jira mirror is visible; this projection does not claim a current remote observation.",
            )
        counts = snapshot.get("status_counts")
        if not isinstance(counts, dict):
            readback = guard.get("readback")
            counts = readback.get("status_counts") if isinstance(readback, dict) else {}
        if not isinstance(counts, dict):
            counts = {}
        mappings = guard.get("reconciled_remote_keys") or {}
        pp385 = mappings.get("PP-TASK-000385") or {}
        pp384 = mappings.get("PP-TASK-000384") or {}
        parity = str(guard.get("parity_status") or "")
        stale = parity != "PARITY_CONFIRMED"
        note = (
            f"Observed live readback {counts.get('To Do', '?')}/"
            f"{counts.get('In Progress', '?')}/{counts.get('Done', '?')} "
            f"from snapshot {snapshot.get('snapshot_id')}; "
            f"PP-TASK-000385->{pp385.get('remote_key', 'unbound')} "
            f"{pp385.get('live_state', '')}; "
            f"PP-TASK-000384->{pp384.get('remote_key', 'unbound')} "
            f"{pp384.get('live_state', '')}. "
            "This projection does not perform a remote write."
        )
        return ApplicationSyncStatus(
            system="Jira",
            mode=str(guard.get("authority_mode") or "SOURCE_CONTROLLED_LOCAL_PLUS_LIVE_READBACK")[
                :100
            ],
            remote_mutation_performed=False,
            stale=stale,
            local_record_count=local_issue_count,
            pending_outbox_count=pending,
            conflict_count=conflicts,
            note=note[:1000],
        )

    def _github_sync_status(self) -> ApplicationSyncStatus:
        return ApplicationSyncStatus(
            system="GitHub",
            mode="LOCAL_ONLY",
            remote_mutation_performed=False,
            stale=True,
            local_record_count=self._count_jsonl("evidence/github_reconciliation.jsonl"),
            pending_outbox_count=self._count_jsonl("evidence/github_outbox.jsonl"),
            conflict_count=self._count_jsonl("evidence/github_conflicts.jsonl"),
            note="Repository-local GitHub governance state is visible; this projection does not claim a current remote observation.",
        )

    @staticmethod
    def _next_transition(issue: dict[str, Any]) -> str | None:
        blockers = issue.get("blockers") or []
        if blockers:
            return "Resolve recorded blocker"
        if issue.get("state") == "IN_PROGRESS":
            return "Complete acceptance criteria and attach evidence"
        return None

    def _evidence_row(self, row: dict[str, Any]) -> ApplicationEvidenceRecord:
        evidence_id = str(row.get("evidence_id") or row.get("id") or "EVIDENCE-UNKNOWN")
        summary = str(
            row.get("summary") or row.get("description") or row.get("claim") or evidence_id
        )
        path_value = row.get("path") or row.get("artifact_path")
        return ApplicationEvidenceRecord(
            evidence_id=evidence_id,
            kind=str(row.get("evidence_type") or row.get("kind") or "EVIDENCE"),
            status=str(row.get("status") or row.get("verification_state") or "RECORDED"),
            summary=summary[:1000],
            path=str(path_value)[:600] if path_value else None,
        )

    def _graph(
        self,
        requirements: list[dict[str, Any]],
        issues: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> ApplicationGraph:
        nodes: list[ApplicationGraphNode] = []
        edges: list[ApplicationGraphEdge] = []
        active_requirements = [
            row
            for row in requirements
            if row.get("implementation_state") != "IMPLEMENTED"
            or str(row.get("requirement_id", "")).startswith("REQ-UX-")
        ]
        for row in active_requirements:
            rid = str(row.get("requirement_id", ""))
            if not rid:
                continue
            nodes.append(
                ApplicationGraphNode(
                    node_id=rid,
                    kind="requirement",
                    label=str(row.get("title") or row.get("statement") or rid)[:500],
                    state=str(row.get("implementation_state", "UNKNOWN")),
                    authoritative_path="plans/_traceability/requirements.jsonl",
                )
            )
        linked_issue_ids = {
            str(jid) for row in active_requirements for jid in (row.get("jira_ids") or [])
        }
        issue_by_id = {str(row.get("local_id")): row for row in issues if row.get("local_id")}
        for jid in sorted(linked_issue_ids):
            issue_row = issue_by_id.get(jid)
            if not issue_row:
                continue
            nodes.append(
                ApplicationGraphNode(
                    node_id=jid,
                    kind="jira",
                    label=str(issue_row.get("title") or jid)[:500],
                    state=str(issue_row.get("state", "UNKNOWN")),
                    authoritative_path=f"jira/{str(issue_row.get('issue_type', 'item')).lower()}s/{jid}.json",
                )
            )
        evidence_ids = {
            str(eid) for row in active_requirements for eid in (row.get("evidence_ids") or [])
        }
        evidence_by_id = {str(row.get("evidence_id") or row.get("id")): row for row in evidence}
        for eid in sorted(evidence_ids):
            evidence_row = evidence_by_id.get(eid)
            if not evidence_row:
                continue
            nodes.append(
                ApplicationGraphNode(
                    node_id=eid,
                    kind="evidence",
                    label=str(
                        evidence_row.get("summary") or evidence_row.get("description") or eid
                    )[:500],
                    state=str(
                        evidence_row.get("status")
                        or evidence_row.get("verification_state")
                        or "RECORDED"
                    ),
                    authoritative_path=str(
                        evidence_row.get("path") or "evidence/EVIDENCE_LEDGER.jsonl"
                    )[:600],
                )
            )
        node_ids = {node.node_id for node in nodes}
        for row in active_requirements:
            rid = str(row.get("requirement_id", ""))
            for jid in row.get("jira_ids") or []:
                if rid in node_ids and str(jid) in node_ids:
                    edges.append(
                        ApplicationGraphEdge(source=rid, target=str(jid), kind="TRACKED_BY")
                    )
            for eid in row.get("evidence_ids") or []:
                if rid in node_ids and str(eid) in node_ids:
                    edges.append(
                        ApplicationGraphEdge(source=rid, target=str(eid), kind="SUPPORTED_BY")
                    )
        truncated = len(nodes) > self.max_graph_nodes
        if truncated:
            kept = nodes[: self.max_graph_nodes]
            kept_ids = {node.node_id for node in kept}
            nodes = kept
            edges = [edge for edge in edges if edge.source in kept_ids and edge.target in kept_ids]
        return ApplicationGraph(nodes=tuple(nodes), edges=tuple(edges), truncated=truncated)
