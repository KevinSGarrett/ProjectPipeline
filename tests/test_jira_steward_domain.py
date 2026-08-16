from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from project_pipeline.domain.jira import (
    JiraAuthorityMode,
    JiraCommentIntent,
    JiraCommentKind,
    JiraConflictKind,
    JiraIssueType,
    JiraLifecycleState,
    JiraMirrorBundle,
    JiraRemoteSnapshot,
    JiraSyncOperationType,
    RemoteJiraIssue,
)
from project_pipeline.domain.state import TaskLifecycleState, task_state_from_jira
from project_pipeline.jira_steward.comments import evaluate_transition
from project_pipeline.jira_steward.reconciliation import (
    JiraReconciler,
    JiraReconciliationPolicy,
    load_jira_reconciliation_policy,
)
from project_pipeline.jira_steward.repository import (
    JiraMirrorRepository,
    export_jira_mirror,
    load_jira_export,
)

ROOT = Path(__file__).resolve().parents[1]


def _bundle(*issues):
    ordered = tuple(sorted(issues, key=lambda item: item.local_id))
    payload = [item.model_dump(mode="json") for item in ordered]
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    return JiraMirrorBundle(
        board_id="PROJECT-PIPELINE-LOCAL",
        project_key="PP",
        issues=ordered,
        issue_count=len(ordered),
        edge_count=sum(len(item.relationships) for item in ordered),
        fingerprint=fingerprint,
    )


def _remote_for(issue, *, key="PP-1", summary=None, status=None):
    reconciler = JiraReconciler()
    state = status or issue.state
    return RemoteJiraIssue(
        remote_id=f"remote-{key}",
        remote_key=key,
        local_id=issue.local_id,
        issue_type_name=issue.issue_type.value.title(),
        normalized_issue_type=issue.issue_type,
        summary=summary or issue.title,
        description_text=reconciler._remote_description(issue),
        status_name=reconciler.policy.preferred_remote_status[state],
        normalized_state=state,
        labels=tuple(reconciler._managed_labels(issue)),
        updated_at_utc="2026-08-14T12:00:00Z",
        version=1,
    )


class JiraStewardDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = JiraMirrorRepository(ROOT)
        cls.issues = cls.repository.load_issues()

    def test_existing_local_mirror_round_trips_through_typed_models(self) -> None:
        expected = json.loads((ROOT / "jira/BOARD_MANIFEST.json").read_text(encoding="utf-8"))[
            "issue_count"
        ]
        self.assertEqual(len(self.issues), expected)
        report = self.repository.validate()
        self.assertTrue(report.valid, report.errors)
        first = self.issues[0]
        self.assertEqual(type(first).model_validate(first.model_dump(mode="json")), first)

    def test_same_count_graph_edge_corruption_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            shutil.copytree(ROOT / "jira", target / "jira")
            graph_path = target / "jira" / "relationships" / "graph.json"
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            graph["edges"][0]["type"] = "CORRUPTED_RELATIONSHIP"
            graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
            report = JiraMirrorRepository(target).validate()
        self.assertFalse(report.valid)
        self.assertIn(
            "stored Jira graph edges differ from canonical issue relationships",
            report.errors,
        )

    def test_export_import_preserves_semantic_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jira-export.json"
            exported = export_jira_mirror(ROOT, path)
            imported = load_jira_export(path)
        self.assertEqual(exported.fingerprint, imported.fingerprint)
        self.assertEqual(exported.issue_count, imported.issue_count)

    def test_comment_intent_rejects_activity_noise(self) -> None:
        with self.assertRaises(ValidationError):
            JiraCommentIntent.create(
                local_id=self.issues[0].local_id,
                kind=JiraCommentKind.WORK_STARTED,
                body="Started editing a file and opened another file in the repository.",
                actor_id="actor:test",
                correlation_id="corr:test",
            )

    def test_comment_intent_accepts_material_project_history(self) -> None:
        intent = JiraCommentIntent.create(
            local_id=self.issues[0].local_id,
            kind=JiraCommentKind.DECISION,
            body="Decision: preserve the source-controlled local issue identity and reconcile remote Jira through the steward.",
            actor_id="actor:test",
            correlation_id="corr:test",
            decision_references=("ADR-001",),
        )
        self.assertTrue(intent.comment_intent_id.startswith("JCOM-"))
        self.assertEqual(len(intent.semantic_fingerprint()), 64)

    def test_done_transition_requires_completion_evidence_and_verification(self) -> None:
        issue = next(item for item in self.issues if item.state is not JiraLifecycleState.DONE)
        readiness = evaluate_transition(
            issue,
            JiraLifecycleState.DONE,
            assigned=True,
            implementation_evidence_present=True,
            branch_present=True,
            required_tests_passed=True,
            acceptance_criteria_verified=False,
            independent_review_complete=True,
            blockers_clear=True,
            completion_evidence_present=False,
        )
        self.assertFalse(readiness.allowed)
        self.assertTrue(any("Acceptance criteria" in reason for reason in readiness.reasons))
        self.assertTrue(any("Completion evidence" in reason for reason in readiness.reasons))

    def test_ready_to_in_progress_requires_assignment(self) -> None:
        issue = next(item for item in self.issues if item.local_id == "PP-TASK-000327")
        ready_issue = issue.model_copy(update={"state": JiraLifecycleState.READY})
        evidence = {
            "branch_present": True,
            "implementation_evidence_present": True,
            "required_tests_passed": True,
            "acceptance_criteria_verified": True,
            "independent_review_complete": True,
            "blockers_clear": True,
            "completion_evidence_present": True,
        }
        assigned = evaluate_transition(
            ready_issue,
            JiraLifecycleState.IN_PROGRESS,
            assigned=True,
            **evidence,
        )
        unassigned = evaluate_transition(
            ready_issue,
            JiraLifecycleState.IN_PROGRESS,
            assigned=False,
            **evidence,
        )
        self.assertTrue(assigned.allowed, assigned.reasons)
        self.assertFalse(unassigned.allowed)
        self.assertTrue(any("assigned" in reason for reason in unassigned.reasons))

    def test_in_progress_to_review_requires_governed_branch_and_tests(self) -> None:
        issue = next(item for item in self.issues if item.local_id == "PP-TASK-000327")
        in_progress_issue = issue.model_copy(update={"state": JiraLifecycleState.IN_PROGRESS})
        evidence = {
            "assigned": True,
            "branch_present": True,
            "implementation_evidence_present": True,
            "required_tests_passed": True,
            "acceptance_criteria_verified": True,
            "independent_review_complete": False,
            "blockers_clear": True,
            "completion_evidence_present": True,
        }

        ready_for_review = evaluate_transition(
            in_progress_issue,
            JiraLifecycleState.REVIEW,
            **evidence,
        )
        missing_branch = evaluate_transition(
            in_progress_issue,
            JiraLifecycleState.REVIEW,
            **{**evidence, "branch_present": False},
        )
        failing_tests = evaluate_transition(
            in_progress_issue,
            JiraLifecycleState.REVIEW,
            **{**evidence, "required_tests_passed": False},
        )

        self.assertTrue(ready_for_review.allowed, ready_for_review.reasons)
        self.assertFalse(missing_branch.allowed)
        self.assertTrue(any("governed branch" in reason for reason in missing_branch.reasons))
        self.assertFalse(failing_tests.allowed)
        self.assertTrue(any("tests" in reason for reason in failing_tests.reasons))

    def test_jira_review_maps_to_internal_review_state(self) -> None:
        self.assertIs(task_state_from_jira("REVIEW"), TaskLifecycleState.IN_REVIEW)

    def test_reconciliation_is_deterministic_and_detects_remote_drift(self) -> None:
        issue = self.issues[0].model_copy(update={"remote_jira_key": None})
        local = _bundle(issue)
        remote_issue = _remote_for(
            issue,
            summary="Remote title drift",
            status=(
                JiraLifecycleState.BACKLOG
                if issue.state is not JiraLifecycleState.BACKLOG
                else JiraLifecycleState.IN_PROGRESS
            ),
        )
        remote = JiraRemoteSnapshot.create(project_key="PP", issues=(remote_issue,))
        reconciler = JiraReconciler()
        first = reconciler.plan(local, remote)
        second = reconciler.plan(local, remote)
        self.assertEqual(first.plan_id, second.plan_id)
        kinds = {item.operation_type for item in first.operations}
        self.assertIn(JiraSyncOperationType.RECORD_REMOTE_MAPPING, kinds)
        self.assertIn(JiraSyncOperationType.UPDATE_REMOTE_FIELDS, kinds)
        self.assertIn(JiraSyncOperationType.TRANSITION_REMOTE_ISSUE, kinds)

    def test_reconciliation_skips_transition_when_remote_status_is_already_preferred(self) -> None:
        issue = self.issues[0].model_copy(update={"state": JiraLifecycleState.READY})
        remote_issue = _remote_for(
            issue,
            status=JiraLifecycleState.BACKLOG,
            summary="Stale remote summary",
        )
        plan = JiraReconciler().plan(
            _bundle(issue),
            JiraRemoteSnapshot.create(project_key="PP", issues=(remote_issue,)),
        )
        self.assertEqual(plan.conflicts, ())
        self.assertEqual(
            [operation.operation_type for operation in plan.operations],
            [JiraSyncOperationType.UPDATE_REMOTE_FIELDS],
        )

    def test_source_controlled_reconciliation_normalizes_preferred_status_alias(self) -> None:
        issue = self.issues[0]
        remote_issue = _remote_for(issue).model_copy(update={"status_name": "Backlog"})
        plan = JiraReconciler().plan(
            _bundle(issue),
            JiraRemoteSnapshot.create(project_key="PP", issues=(remote_issue,)),
        )
        self.assertEqual(plan.conflicts, ())
        transition = next(
            operation
            for operation in plan.operations
            if operation.operation_type is JiraSyncOperationType.TRANSITION_REMOTE_ISSUE
        )
        self.assertEqual(transition.payload["from_status"], "Backlog")
        self.assertEqual(transition.payload["target_status"], "To Do")

    def test_duplicate_and_remote_only_mappings_become_explicit_conflicts(self) -> None:
        issue = self.issues[0]
        local = _bundle(issue)
        first = _remote_for(issue, key="PP-1")
        second = _remote_for(issue, key="PP-2")
        remote_only = RemoteJiraIssue(
            remote_id="remote-3",
            remote_key="PP-3",
            issue_type_name="Task",
            normalized_issue_type=JiraIssueType.TASK,
            summary="Remote only",
            status_name="Backlog",
            normalized_state=JiraLifecycleState.BACKLOG,
            updated_at_utc="2026-08-14T12:00:00Z",
            version=1,
        )
        plan = JiraReconciler().plan(
            local,
            JiraRemoteSnapshot.create(project_key="PP", issues=(first, second, remote_only)),
        )
        kinds = {item.kind for item in plan.conflicts}
        self.assertIn(JiraConflictKind.DUPLICATE_REMOTE_MAPPING, kinds)
        self.assertIn(JiraConflictKind.REMOTE_ONLY_ISSUE, kinds)

    def test_human_review_can_be_required_for_collaborative_remote_done(self) -> None:
        issue = next(item for item in self.issues if item.state is not JiraLifecycleState.DONE)
        local = _bundle(issue)
        remote = JiraRemoteSnapshot.create(
            project_key="PP",
            issues=(_remote_for(issue, status=JiraLifecycleState.DONE),),
        )
        policy = JiraReconciliationPolicy(
            authority_mode=JiraAuthorityMode.REMOTE_COLLABORATIVE,
            require_human_for_remote_done=True,
        )
        plan = JiraReconciler(policy).plan(local, remote)
        self.assertTrue(any(item.requires_human_approval for item in plan.operations))
        self.assertTrue(
            any(item.kind is JiraConflictKind.HUMAN_DECISION_REQUIRED for item in plan.conflicts)
        )

    def test_project_policy_preserves_human_gate_for_remote_done(self) -> None:
        self.assertTrue(JiraReconciliationPolicy().require_human_for_remote_done)
        policy = load_jira_reconciliation_policy(ROOT)
        self.assertTrue(policy.require_human_for_remote_done)

    def test_create_operations_are_parent_first(self) -> None:
        epic = next(item for item in self.issues if item.issue_type is JiraIssueType.EPIC)
        story = next(item for item in self.issues if item.parent == epic.local_id)
        local = _bundle(story, epic)
        plan = JiraReconciler().plan(local, JiraRemoteSnapshot.create(project_key="PP", issues=()))
        self.assertEqual(plan.operations[0].local_id, epic.local_id)
        self.assertEqual(plan.operations[1].local_id, story.local_id)

    def test_plan_projects_task_hierarchy_and_dependencies_as_links(self) -> None:
        task = next(
            item
            for item in self.issues
            if item.issue_type is JiraIssueType.TASK and item.dependencies
        )
        story = next(item for item in self.issues if item.local_id == task.parent)
        dependency = next(item for item in self.issues if item.local_id == task.dependencies[0])
        local = _bundle(story, task, dependency)
        plan = JiraReconciler().plan(local, JiraRemoteSnapshot.create(project_key="PP", issues=()))
        links = [
            item.payload
            for item in plan.operations
            if item.operation_type is JiraSyncOperationType.CREATE_REMOTE_LINK
        ]
        self.assertIn(
            {
                "link_type": "Parent Of",
                "outward_local_id": story.local_id,
                "inward_local_id": task.local_id,
                "semantic_kind": "LOCAL_HIERARCHY",
            },
            links,
        )
        self.assertIn(
            {
                "link_type": "Depends On",
                "outward_local_id": task.local_id,
                "inward_local_id": dependency.local_id,
                "semantic_kind": "LOCAL_DEPENDENCY",
            },
            links,
        )

    def test_remote_description_preserves_structured_work_item_semantics(self) -> None:
        issue = self.issues[0]
        description = JiraReconciler._remote_description(issue)
        for heading in (
            "Local Work Item",
            "Objective",
            "Requirements / Traceability",
            "Acceptance Criteria",
            "Required Tests",
            "Evidence Required",
            "Security Impact",
            "Rollback / Recovery",
        ):
            self.assertIn(heading, description)
        self.assertIn(issue.local_id, description)

    def test_description_comparison_ignores_adf_whitespace_round_trip(self) -> None:
        self.assertEqual(
            JiraReconciler._normalize_description("Heading\n\n- one\n  detail"),
            JiraReconciler._normalize_description("Heading\n- one\ndetail"),
        )

    def test_default_backlog_status_matches_classic_project_workflow(self) -> None:
        policy = JiraReconciliationPolicy()
        self.assertEqual(
            policy.status_mapping.remote_to_internal["To Do"], JiraLifecycleState.BACKLOG
        )
        self.assertEqual(policy.preferred_remote_status[JiraLifecycleState.BACKLOG], "To Do")
