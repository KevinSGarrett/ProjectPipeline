from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from project_pipeline.requirement_views import validate_requirement_views, write_requirement_views

ROOT = Path(__file__).resolve().parents[1]


class RequirementViewTests(unittest.TestCase):
    def test_generated_requirement_views_are_current(self) -> None:
        self.assertEqual([], validate_requirement_views(ROOT))

    def test_requirement_view_generation_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            shutil.copytree(ROOT / "plans", target / "plans")
            first = write_requirement_views(target)
            first_content = {
                path: (target / path).read_text(encoding="utf-8") for path in first["paths"]
            }
            second = write_requirement_views(target)
            second_content = {
                path: (target / path).read_text(encoding="utf-8") for path in second["paths"]
            }
            self.assertEqual(first, second)
            self.assertEqual(first_content, second_content)
            self.assertEqual([], validate_requirement_views(target))
