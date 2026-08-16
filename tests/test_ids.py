from __future__ import annotations

import unittest

from project_pipeline.ids import ACCEPTANCE_ID, ISSUE_ID, PLAN_ID, REQUIREMENT_ID, SOURCE_REFERENCE


class IdentifierTests(unittest.TestCase):
    def test_valid_identifiers_match(self) -> None:
        self.assertIsNotNone(REQUIREMENT_ID.fullmatch("REQ-CTRL-0001"))
        self.assertIsNotNone(PLAN_ID.fullmatch("PLAN-CTRL-001"))
        self.assertIsNotNone(ISSUE_ID.fullmatch("PP-TASK-000001"))
        self.assertIsNotNone(ACCEPTANCE_ID.fullmatch("AC-PP-000001-01"))
        self.assertIsNotNone(SOURCE_REFERENCE.fullmatch("SRC-003:L000040-L000083"))

    def test_invalid_identifiers_do_not_match(self) -> None:
        self.assertIsNone(REQUIREMENT_ID.fullmatch("REQ-1"))
        self.assertIsNone(ISSUE_ID.fullmatch("TASK-1"))
        self.assertIsNone(SOURCE_REFERENCE.fullmatch("SRC-003:40-83"))
