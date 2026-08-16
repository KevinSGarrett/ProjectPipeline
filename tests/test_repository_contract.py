from __future__ import annotations

import unittest
from pathlib import Path

from project_pipeline.validation import RepositoryValidator

ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_repository_contract_has_no_errors(self) -> None:
        report = RepositoryValidator(ROOT).validate()
        self.assertEqual([], [item.as_dict() for item in report.errors], report.render())
