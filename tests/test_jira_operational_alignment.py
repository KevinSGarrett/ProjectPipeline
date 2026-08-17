from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from project_pipeline.domain.state import task_state_from_jira
from project_pipeline.io import read_json, write_json
from project_pipeline.jira import rebuild_jira_indexes
from project_pipeline.jira_steward.alignment import validate_jira_operational_alignment

ROOT = Path(__file__).resolve().parents[1]


def _copy_issue_chain(root: Path, local_id: str) -> list[dict[str, object]]:
    copied: list[dict[str, object]] = []
    current = local_id
    while current:
        kind = {
            "EPIC": "epics",
            "STORY": "stories",
            "TASK": "tasks",
            "SUBTASK": "subtasks",
            "BUG": "bugs",
            "SPIKE": "spikes",
        }[current.split("-")[1]]
        source = ROOT / "jira" / kind / f"{current}.json"
        target = root / "jira" / kind / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        issue = read_json(target)
        copied.append(issue)
        current = str(issue.get("parent") or "")
    copied_ids = {str(item["local_id"]) for item in copied}
    for issue in copied:
        issue["dependencies"] = [
            item for item in issue.get("dependencies", []) if item in copied_ids
        ]
        issue["blockers"] = [item for item in issue.get("blockers", []) if item in copied_ids]
        issue["relationships"] = [
            item for item in issue.get("relationships", []) if item.get("target") in copied_ids
        ]
        kind = {
            "EPIC": "epics",
            "STORY": "stories",
            "TASK": "tasks",
            "SUBTASK": "subtasks",
            "BUG": "bugs",
            "SPIKE": "spikes",
        }[str(issue["local_id"]).split("-")[1]]
        write_json(root / "jira" / kind / f"{issue['local_id']}.json", issue)
    return copied


@pytest.fixture
def aligned_root(tmp_path: Path) -> tuple[Path, Path, list[dict[str, object]]]:
    issues = _copy_issue_chain(tmp_path, "PP-TASK-000345")
    rebuild_jira_indexes(tmp_path)
    database = tmp_path / "state.db"
    snapshots: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE task_states (task_id TEXT PRIMARY KEY, state TEXT)")
        connection.execute(
            "CREATE TABLE jira_remote_snapshots (snapshot_id TEXT PRIMARY KEY, snapshot_json TEXT)"
        )
        for issue in issues:
            connection.execute(
                "INSERT INTO task_states VALUES (?, ?)",
                (issue["local_id"], task_state_from_jira(str(issue["state"])).value),
            )
            observation = issue.get("last_observed_remote_state")
            if not isinstance(observation, dict):
                continue
            snapshot_id = str(observation["snapshot_id"])
            snapshot = snapshots.setdefault(snapshot_id, {"snapshot_id": snapshot_id, "issues": []})
            snapshot["issues"].append(
                {
                    "local_id": issue["local_id"],
                    "remote_key": observation.get("remote_key"),
                    "status_name": observation.get("status_name"),
                }
            )
        for snapshot_id, snapshot in snapshots.items():
            connection.execute(
                "INSERT OR REPLACE INTO jira_remote_snapshots VALUES (?, ?)",
                (snapshot_id, json.dumps(snapshot)),
            )
    return tmp_path, database, issues


def test_jira_source_database_views_and_remote_readback_align(
    aligned_root: tuple[Path, Path, list[dict[str, object]]],
) -> None:
    root, database, _ = aligned_root
    assert validate_jira_operational_alignment(root, database).errors == ()


def test_jira_database_state_drift_fails_closed(
    aligned_root: tuple[Path, Path, list[dict[str, object]]],
) -> None:
    root, database, _ = aligned_root
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE task_states SET state = 'BACKLOG' WHERE task_id = 'PP-TASK-000345'"
        )
    errors = validate_jira_operational_alignment(root, database).errors
    assert any("PP-TASK-000345" in error and "state mismatch" in error for error in errors)


def test_jira_generated_projection_drift_fails_closed(
    aligned_root: tuple[Path, Path, list[dict[str, object]]],
) -> None:
    root, database, _ = aligned_root
    index = root / "jira/indexes/issues_by_id.json"
    document = read_json(index)
    document["PP-TASK-000345"]["state"] = "BACKLOG"
    write_json(index, document)
    errors = validate_jira_operational_alignment(root, database).errors
    assert "stored Jira issue-by-id index differs from canonical source issues" in errors


def test_jira_remote_observation_must_match_its_cited_snapshot(
    aligned_root: tuple[Path, Path, list[dict[str, object]]],
) -> None:
    root, database, issues = aligned_root
    task = next(item for item in issues if item["local_id"] == "PP-TASK-000345")
    observation = task["last_observed_remote_state"]
    assert isinstance(observation, dict)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT snapshot_json FROM jira_remote_snapshots WHERE snapshot_id = ?",
            (observation["snapshot_id"],),
        ).fetchone()
        snapshot = json.loads(str(row[0]))
        snapshot["issues"][0]["status_name"] = "Incorrect Status"
        connection.execute(
            "UPDATE jira_remote_snapshots SET snapshot_json = ? WHERE snapshot_id = ?",
            (json.dumps(snapshot), observation["snapshot_id"]),
        )
    errors = validate_jira_operational_alignment(root, database).errors
    assert any("remote observation status differs" in error for error in errors)
