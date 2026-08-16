from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from project_pipeline.jira import rebuild_jira_indexes

ROOT = Path(__file__).resolve().parents[1]


class JiraRebuildTests(unittest.TestCase):
    def test_rebuild_is_deterministic_and_preserves_all_work_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            shutil.copytree(ROOT / "jira", target / "jira")
            first = rebuild_jira_indexes(target)
            first_graph = json.loads(
                (target / "jira/relationships/graph.json").read_text(encoding="utf-8")
            )
            second = rebuild_jira_indexes(target)
            second_graph = json.loads(
                (target / "jira/relationships/graph.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first, second)
            self.assertEqual(first_graph, second_graph)
            expected_issue_count = sum(
                1
                for folder in ("epics", "stories", "tasks", "subtasks", "bugs", "spikes")
                for _ in (ROOT / "jira" / folder).glob("PP-*.json")
            )
            self.assertEqual(first["status"]["issue_count"], expected_issue_count)
            self.assertEqual(first["status"]["requirements_referenced"], 351)
            edges = first_graph["edges"]
            identities = {(edge["from"], edge["to"], edge["type"]) for edge in edges}
            self.assertEqual(len(edges), len(identities))
            expected_dependencies = {
                (issue["local_id"], dependency, "DEPENDS_ON")
                for folder in ("epics", "stories", "tasks", "subtasks", "bugs", "spikes")
                for path in (ROOT / "jira" / folder).glob("PP-*.json")
                for issue in (json.loads(path.read_text(encoding="utf-8")),)
                for dependency in issue.get("dependencies", [])
            }
            self.assertTrue(expected_dependencies)
            self.assertTrue(expected_dependencies <= identities)
