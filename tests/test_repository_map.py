from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_pipeline.repository_map import build_repository_map, write_repository_map


class RepositoryMapTests(unittest.TestCase):
    def test_map_groups_semantic_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plans").mkdir()
            (root / "plans" / "a.md").write_text("# A\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            result = build_repository_map(root)
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["semantic_index"]["plans"], ["plans/a.md"])
            written = write_repository_map(root)
            self.assertGreaterEqual(written["file_count"], 2)
            self.assertTrue((root / "docs" / "generated" / "REPOSITORY_MAP.json").exists())
