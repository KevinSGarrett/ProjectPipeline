from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from project_pipeline.jira_steward.adapter import AtlassianJiraCloudAdapter
from project_pipeline.jira_steward.identity import (
    classify_identity_by_remote_key_only,
    classify_identity_parity,
    classify_status_parity,
    derive_remote_local_id,
)
from project_pipeline.jira_steward.sync_guard import evaluate_jira_sync_guard


def _local(
    local_id: str = "PP-TASK-000385",
    *,
    remote_key: str | None = None,
    state: str = "BACKLOG",
) -> dict[str, object]:
    return {
        "local_id": local_id,
        "remote_jira_key": remote_key,
        "state": state,
        "last_observed_remote_state": None,
    }


def _remote(
    remote_key: str = "PP-391",
    *,
    labels: tuple[str, ...] = ("pp-local-id:PP-TASK-000385", "pp-task-000385"),
    description: str = "Local ID: PP-TASK-000385\nConfirmed remote key: PP-391",
    status: str = "In Progress",
    local_id: str | None = None,
) -> dict[str, object]:
    return {
        "remote_key": remote_key,
        "local_id": local_id,
        "labels": list(labels),
        "description_text": description,
        "status_name": status,
        "version": 4,
    }


def test_derive_unique_local_id_from_label_and_description() -> None:
    derivation = derive_remote_local_id(
        labels=("autonomy-runtime", "pp-local-id:PP-TASK-000385", "pp-task-000385"),
        description="Local ID: PP-TASK-000385\nParent local ID: PP-STORY-000143",
    )
    assert derivation.status == "UNIQUE"
    assert derivation.local_id == "PP-TASK-000385"


def test_derive_fails_closed_on_duplicate_local_ids() -> None:
    derivation = derive_remote_local_id(
        labels=("pp-local-id:PP-TASK-000385",),
        description="Local ID: PP-TASK-000384",
    )
    assert derivation.status == "CONFLICT"
    assert derivation.fail_closed()
    assert derivation.local_id is None


def test_missing_mapping_with_unique_remote_match_is_reconciliation_required() -> None:
    result = classify_identity_parity(
        local_issues=[_local()],
        remote_issues=[_remote()],
    )
    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.matches[0].remote_key == "PP-391"
    assert result.matches[0].local_remote_key is None
    assert any("remote_jira_key is null" in reason for reason in result.reasons)


def test_legacy_key_only_match_misses_unique_label_identity() -> None:
    assert (
        classify_identity_by_remote_key_only(local_remote_key=None, remote_key="PP-391")
        == "NO_DIFFERENCE"
    )


def test_duplicate_remote_mapping_fails_closed_and_does_not_write() -> None:
    result = classify_identity_parity(
        local_issues=[_local()],
        remote_issues=[
            _remote("PP-391"),
            _remote("PP-399", description="Local ID: PP-TASK-000385"),
        ],
    )
    assert result.status == "FAIL_CLOSED"
    assert any("duplicate remote mapping" in reason for reason in result.reasons)


def test_conflicting_declared_and_derived_identity_fails_closed() -> None:
    result = classify_identity_parity(
        local_issues=[_local()],
        remote_issues=[_remote(local_id="PP-TASK-000384")],
    )
    assert result.status == "FAIL_CLOSED"


def test_status_parity_requires_the_same_complete_snapshot() -> None:
    issues = [_remote()]
    assert (
        classify_status_parity(
            local_issues=[_local(remote_key="PP-391")],
            remote_issues=issues,
            snapshot_id="JSNAP-A",
            expected_snapshot_id="JSNAP-B",
        )
        == "FAIL_CLOSED"
    )
    assert (
        classify_status_parity(
            local_issues=[_local()],
            remote_issues=issues,
            snapshot_id="JSNAP-A",
            expected_snapshot_id="JSNAP-A",
        )
        == "RECONCILIATION_REQUIRED"
    )


def test_adapter_extracts_local_id_from_description_when_label_prefix_absent() -> None:
    adapter = AtlassianJiraCloudAdapter(
        base_url="https://example.atlassian.net",
        user_email="user@example.com",
        api_token="secret-token",
    )
    issue = adapter._parse_issue(
        {
            "id": "25365",
            "key": "PP-391",
            "fields": {
                "summary": "Pass unattended qualification",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Local ID: PP-TASK-000385"},
                            ],
                        }
                    ],
                },
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Task"},
                "labels": ["autonomy-runtime"],
                "updated": "2026-08-19T22:28:01.000+0000",
                "comment": {"comments": []},
                "issuelinks": [],
                "attachment": [],
            },
        }
    )
    assert issue.local_id == "PP-TASK-000385"


def test_stale_guard_is_rejected_by_fingerprint_time_and_remote_version(tmp_path) -> None:
    jira = tmp_path / "jira"
    reports = jira / "reports"
    reports.mkdir(parents=True)
    (jira / "tasks").mkdir()
    payload = {
        "local_mirror_fingerprint": "0" * 64,
        "parity_status": "PARITY_CONFIRMED",
        "identity_parity": "NO_DIFFERENCE",
        "readback_verified": True,
        "receipt_id": "JREC-54CE8D5BF4557A09F0B2",
        "plan_id": "JPLAN-3618FC1CD42B00FA927F",
        "generated_at_utc": "2026-08-19T19:37:39Z",
        "remote_snapshot_id": "JSNAP-OLD",
        "remote_version": "1",
        "reconciled_remote_keys": {"PP-TASK-000384": {"remote_key": "PP-393"}},
        "readback": {"status_counts": {"To Do": 360, "In Progress": 13, "Done": 20}},
        "local_reconciliation_pending_remote": False,
    }
    (reports / "jira_sync_guard.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    result = evaluate_jira_sync_guard(
        tmp_path,
        current_remote_version="2",
        latest_write_at_utc=later,
    )
    assert result.passes is False
    joined = " ".join(result.reasons)
    assert "stale" in joined
    assert "later merge or Jira write" in joined
    assert "remote version" in joined


def test_count_drift_and_unknown_write_fail_closed(tmp_path) -> None:
    jira = tmp_path / "jira"
    reports = jira / "reports"
    reports.mkdir(parents=True)
    (jira / "epics").mkdir()
    (jira / "stories").mkdir()
    (jira / "tasks").mkdir()
    (jira / "subtasks").mkdir()
    (jira / "bugs").mkdir()
    payload = {
        "local_mirror_fingerprint": "",
        "parity_status": "PARITY_CONFIRMED",
        "identity_parity": "NO_DIFFERENCE",
        "readback_verified": True,
        "receipt_id": "JREC-1",
        "plan_id": "JPLAN-1",
        "generated_at_utc": "2026-08-19T19:37:39Z",
        "remote_snapshot_id": "JSNAP-A",
        "remote_version": "1",
        "reconciled_remote_keys": {},
        "readback": {"status_counts": {"To Do": 360, "In Progress": 13, "Done": 20}},
        "local_reconciliation_pending_remote": False,
    }
    (reports / "jira_sync_guard.json").write_text(json.dumps(payload), encoding="utf-8")
    result = evaluate_jira_sync_guard(
        tmp_path,
        current_remote={
            "snapshot_id": "JSNAP-A",
            "issues": [_remote()],
            "status_counts": {"To Do": 359, "In Progress": 14, "Done": 20},
        },
    )
    assert result.passes is False
    assert any("status counts drifted" in reason for reason in result.reasons)


def test_pp385_split_brain_fixture_requires_reconciliation() -> None:
    local = _local(remote_key=None, state="BACKLOG")
    remote = _remote()
    stale_guard = {
        "parity_status": "PARITY_CONFIRMED",
        "identity_parity": "NO_DIFFERENCE",
        "readback": {"status_counts": {"To Do": 360, "In Progress": 13, "Done": 20}},
    }
    identity = classify_identity_parity(local_issues=[local], remote_issues=[remote])
    legacy = classify_identity_by_remote_key_only(local_remote_key=None, remote_key="PP-391")
    assert remote["status_name"] == "In Progress"
    assert local["remote_jira_key"] is None
    assert local["last_observed_remote_state"] is None
    assert local["state"] == "BACKLOG"
    assert stale_guard["parity_status"] == "PARITY_CONFIRMED"
    assert stale_guard["identity_parity"] == "NO_DIFFERENCE"
    assert stale_guard["readback"]["status_counts"] != {
        "To Do": 359,
        "In Progress": 14,
        "Done": 20,
    }
    assert legacy == "NO_DIFFERENCE"
    assert identity.status == "RECONCILIATION_REQUIRED"
    assert identity.matches[0].remote_key == "PP-391"


def test_read_before_retry_unknown_outcome_is_reconciliation_required() -> None:
    result = classify_identity_parity(
        local_issues=[_local()],
        remote_issues=[_remote()],
    )
    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.requires_reconciliation
