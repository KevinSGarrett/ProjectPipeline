import unittest
from pathlib import Path

from project_pipeline.jira_steward import validate_jira_steward_foundation

ROOT = Path(__file__).resolve().parents[1]


class JiraStewardValidationTests(unittest.TestCase):
    def test_jira_steward_foundation_is_self_validating(self) -> None:
        self.assertEqual(validate_jira_steward_foundation(ROOT), [])
