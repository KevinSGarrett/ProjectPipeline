from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_pipeline.domain.state import task_state_from_jira
from project_pipeline.jira_steward.repository import JiraMirrorRepository


@dataclass(frozen=True, slots=True)
class JiraOperationalAlignmentReport:
    source_issue_count: int
    database_issue_count: int
    observed_snapshot_count: int
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "source_issue_count": self.source_issue_count,
            "database_issue_count": self.database_issue_count,
            "observed_snapshot_count": self.observed_snapshot_count,
            "valid": self.valid,
            "errors": list(self.errors),
        }


def _read_only_connection(database: Path) -> sqlite3.Connection:
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def validate_jira_operational_alignment(
    root: Path,
    database: Path,
) -> JiraOperationalAlignmentReport:
    """Compare canonical Jira source, generated views, Control state, and cited readback."""

    root = root.resolve()
    issues = JiraMirrorRepository(root).load_issues()
    source = {item.local_id: item for item in issues}
    errors = list(JiraMirrorRepository(root).validate().errors)
    if not database.exists():
        errors.append(f"authoritative state database is missing: {database}")
        return JiraOperationalAlignmentReport(len(source), 0, 0, tuple(sorted(set(errors))))

    snapshot_cache: dict[str, dict[str, Any]] = {}
    with _read_only_connection(database) as connection:
        task_rows = connection.execute(
            "SELECT task_id, state FROM task_states ORDER BY task_id"
        ).fetchall()
        database_states = {str(row["task_id"]): str(row["state"]) for row in task_rows}
        if set(database_states) != set(source):
            missing = sorted(set(source) - set(database_states))
            extra = sorted(set(database_states) - set(source))
            if missing:
                errors.append("database is missing canonical Jira issues: " + ", ".join(missing))
            if extra:
                errors.append(
                    "database contains issues absent from Jira source: " + ", ".join(extra)
                )
        for issue_id in sorted(set(source) & set(database_states)):
            expected = task_state_from_jira(source[issue_id].state.value).value
            observed = database_states[issue_id]
            if expected != observed:
                errors.append(
                    f"Jira source/database state mismatch for {issue_id}: {expected} != {observed}"
                )

        for issue in issues:
            observation = issue.last_observed_remote_state
            if not observation:
                continue
            snapshot_id = str(observation.get("snapshot_id", ""))
            if not snapshot_id:
                errors.append(f"remote observation lacks snapshot identity: {issue.local_id}")
                continue
            if snapshot_id not in snapshot_cache:
                row = connection.execute(
                    "SELECT snapshot_json FROM jira_remote_snapshots WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                if row is None:
                    errors.append(
                        f"cited remote snapshot is absent from the authoritative database: {snapshot_id}"
                    )
                    snapshot_cache[snapshot_id] = {}
                else:
                    snapshot_cache[snapshot_id] = json.loads(str(row["snapshot_json"]))
            snapshot = snapshot_cache[snapshot_id]
            remote_key = str(observation.get("remote_key", issue.remote_jira_key or ""))
            observed_issue = next(
                (
                    item
                    for item in snapshot.get("issues", [])
                    if item.get("remote_key") == remote_key
                    or item.get("local_id") == issue.local_id
                ),
                None,
            )
            if observed_issue is None:
                errors.append(
                    f"cited remote snapshot does not contain {issue.local_id}/{remote_key}: {snapshot_id}"
                )
                continue
            expected_status = str(observation.get("status_name", ""))
            if str(observed_issue.get("status_name", "")) != expected_status:
                errors.append(
                    f"remote observation status differs from cited snapshot for {issue.local_id}: "
                    f"{expected_status} != {observed_issue.get('status_name')}"
                )

    return JiraOperationalAlignmentReport(
        source_issue_count=len(source),
        database_issue_count=len(database_states),
        observed_snapshot_count=len(snapshot_cache),
        errors=tuple(sorted(set(errors))),
    )
