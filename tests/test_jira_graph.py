from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JiraGraphTests(unittest.TestCase):
    def test_graph_has_no_dangling_edges_or_orphan_epics(self) -> None:
        issues = [
            json.loads(line)
            for line in (ROOT / "jira" / "indexes" / "issues.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        graph = json.loads(
            (ROOT / "jira" / "relationships" / "graph.json").read_text(encoding="utf-8")
        )
        ids = {item["local_id"] for item in issues}
        self.assertEqual({node["id"] for node in graph["nodes"]}, ids)
        for edge in graph["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)
        child_count = Counter(item["parent"] for item in issues if item["parent"])
        for item in issues:
            if item["issue_type"] == "EPIC":
                self.assertGreater(child_count[item["local_id"]], 0)

    def test_board_counts_match_issue_index(self) -> None:
        issues = [
            json.loads(line)
            for line in (ROOT / "jira" / "indexes" / "issues.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        board = json.loads((ROOT / "jira" / "BOARD_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(board["issue_count"], len(issues))
        counts = Counter(item["issue_type"] for item in issues)
        expected = {
            kind: counts.get(kind, 0)
            for kind in ("BUG", "EPIC", "SPIKE", "STORY", "SUBTASK", "TASK")
        }
        self.assertEqual(board["counts_by_type"], expected)
