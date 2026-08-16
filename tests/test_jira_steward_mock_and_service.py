from __future__ import annotations

import unittest
from pathlib import Path

from project_pipeline.contracts import (
    ActionIntent,
    AdapterErrorCategory,
    ApprovalState,
    RiskLevel,
)
from project_pipeline.domain.jira import (
    JiraAuthorityMode,
    JiraCommentIntent,
    JiraCommentKind,
    JiraReconciliationPlan,
    JiraRemoteSnapshot,
    jira_sync_identifier,
)
from project_pipeline.jira_steward import MockJiraAdapter
from project_pipeline.jira_steward.persistence import JiraSyncStore
from project_pipeline.jira_steward.reconciliation import JiraReconciler, JiraReconciliationPolicy
from project_pipeline.jira_steward.repository import JiraMirrorRepository
from project_pipeline.jira_steward.service import JiraSteward, JiraStewardError

ROOT = Path(__file__).resolve().parents[1]


def _single_create_plan():
    local = JiraMirrorRepository(ROOT).bundle()
    empty = JiraRemoteSnapshot.create(project_key="PP", issues=())
    full = JiraReconciler().plan(local, empty)
    operation = next(item for item in full.operations if item.payload.get("issue_type") == "EPIC")
    plan = JiraReconciliationPlan(
        plan_id=jira_sync_identifier("JPLAN", "service-test", operation.operation_id),
        project_key="PP",
        authority_mode=JiraAuthorityMode.SOURCE_CONTROLLED_LOCAL,
        local_fingerprint=local.fingerprint,
        remote_snapshot_id=empty.snapshot_id,
        remote_fingerprint=empty.fingerprint,
        operations=(operation,),
        conflicts=(),
    )
    return empty, plan


def _intent(*, approved=True, operation="jira.sync", target="PP"):
    return ActionIntent(
        actor_id="actor:test",
        authority="jira.steward",
        target=target,
        operation=operation,
        idempotency_key="approved-jira-action-0001",
        approval_state=ApprovalState.APPROVED if approved else ApprovalState.REQUIRED,
        correlation_id="corr:test",
        risk=RiskLevel.HIGH,
    )


class JiraStewardMockAndServiceTests(unittest.TestCase):
    def test_mock_pagination_reads_every_issue_exactly_once(self) -> None:
        adapter = MockJiraAdapter(project_key="PP", page_size=2)
        for number in range(1, 6):
            adapter.seed_issue(
                remote_key=f"PP-{number}",
                local_id=None,
                summary=f"Issue {number}",
            )
        observed = tuple(adapter.iter_issues("PP", page_size=100))
        self.assertEqual([item.remote_key for item in observed], [f"PP-{n}" for n in range(1, 6)])
        self.assertEqual(adapter.pages_observed, 3)

    def test_dry_run_persists_plan_without_remote_writes(self) -> None:
        snapshot, plan = _single_create_plan()
        adapter = MockJiraAdapter(project_key="PP")
        with JiraSyncStore(":memory:", ROOT) as store:
            store.put_snapshot(snapshot)
            steward = JiraSteward(
                root=ROOT,
                adapter=adapter,
                store=store,
                policy=JiraReconciliationPolicy(),
            )
            receipt = steward.dry_run(plan, actor_id="actor:test", correlation_id="corr:test")
            self.assertEqual(receipt.result, "DRY_RUN")
            self.assertFalse(any(call[0] == "create_issue" for call in adapter.calls))
            self.assertEqual(store.status("PP")["operation_states"], {"PLANNED": 1})

    def test_apply_requires_approved_jira_steward_intent(self) -> None:
        snapshot, plan = _single_create_plan()
        with JiraSyncStore(":memory:", ROOT) as store:
            store.put_snapshot(snapshot)
            steward = JiraSteward(
                root=ROOT,
                adapter=MockJiraAdapter(project_key="PP"),
                store=store,
                policy=JiraReconciliationPolicy(),
            )
            with self.assertRaises(JiraStewardError):
                steward.apply(
                    plan,
                    action_intent=_intent(approved=False),
                    authorization_id="auth:test",
                )

    def test_apply_is_idempotent_after_successful_creation(self) -> None:
        snapshot, plan = _single_create_plan()
        adapter = MockJiraAdapter(project_key="PP")
        with JiraSyncStore(":memory:", ROOT) as store:
            store.put_snapshot(snapshot)
            steward = JiraSteward(
                root=ROOT,
                adapter=adapter,
                store=store,
                policy=JiraReconciliationPolicy(),
            )
            first = steward.apply(plan, action_intent=_intent(), authorization_id="auth:test")
            second = steward.apply(plan, action_intent=_intent(), authorization_id="auth:test")
            self.assertEqual(first.result, "APPLIED")
            self.assertEqual(second.result, "APPLIED")
            self.assertEqual(sum(call[0] == "create_issue" for call in adapter.calls), 1)

    def test_unknown_write_outcome_stops_retries_and_requires_reconciliation(self) -> None:
        snapshot, plan = _single_create_plan()
        adapter = MockJiraAdapter(project_key="PP")
        adapter.schedule_failure("create_issue", AdapterErrorCategory.UNKNOWN_OUTCOME)
        with JiraSyncStore(":memory:", ROOT) as store:
            store.put_snapshot(snapshot)
            steward = JiraSteward(
                root=ROOT,
                adapter=adapter,
                store=store,
                policy=JiraReconciliationPolicy(),
            )
            first = steward.apply(plan, action_intent=_intent(), authorization_id="auth:test")
            second = steward.apply(plan, action_intent=_intent(), authorization_id="auth:test")
            self.assertEqual(first.result, "RECONCILIATION_REQUIRED")
            self.assertEqual(second.result, "RECONCILIATION_REQUIRED")
            self.assertEqual(sum(call[0] == "create_issue" for call in adapter.calls), 1)
            self.assertEqual(len(first.unknown_outcome_operation_ids), 1)

    def test_meaningful_comment_posts_through_steward(self) -> None:
        local = (
            JiraMirrorRepository(ROOT).issues if False else JiraMirrorRepository(ROOT).load_issues()
        )
        issue = local[0]
        adapter = MockJiraAdapter(project_key="PP")
        remote = adapter.seed_issue(remote_key="PP-1", local_id=issue.local_id, summary=issue.title)
        with JiraSyncStore(":memory:", ROOT) as store:
            store.initialize()
            store.put_remote_mapping(
                local_id=issue.local_id,
                remote_key=remote.remote_key,
                provider_id=adapter.provider_id,
                source_operation_id=None,
                remote_fingerprint=remote.semantic_fingerprint(),
            )
            steward = JiraSteward(
                root=ROOT,
                adapter=adapter,
                store=store,
                policy=JiraReconciliationPolicy(),
            )
            comment = JiraCommentIntent.create(
                local_id=issue.local_id,
                kind=JiraCommentKind.VALIDATION_EVIDENCE,
                body="Validation evidence recorded: the Jira steward contract suite completed successfully.",
                actor_id="actor:test",
                correlation_id="corr:test",
                evidence_references=("EVIDENCE-000001",),
            )
            result = steward.post_comment(
                comment,
                action_intent=_intent(operation="jira.comment", target=issue.local_id),
                authorization_id="auth:test",
            )
            self.assertEqual(result["remote_key"], "PP-1")
            self.assertEqual(sum(call[0] == "add_comment" for call in adapter.calls), 1)
