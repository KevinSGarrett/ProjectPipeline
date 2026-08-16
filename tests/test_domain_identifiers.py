from __future__ import annotations

import unittest

from project_pipeline.domain import (
    DomainIdentifier,
    IdentifierKind,
    deterministic_identifier,
    project_identifier,
)


class DomainIdentifierTests(unittest.TestCase):
    def test_project_identifier_normalizes_without_duplicate_prefix(self) -> None:
        self.assertEqual(project_identifier("Project Pipeline").value, "PROJECT-PIPELINE")
        self.assertEqual(project_identifier("  Project—Pipeline  ").value, "PROJECT-PIPELINE")

    def test_digest_identifiers_are_deterministic_and_kind_scoped(self) -> None:
        first = deterministic_identifier(
            IdentifierKind.TRACE_LINK, "REQ-ARCH-0008", "PLAN", "PLAN-ARCH-001"
        )
        second = deterministic_identifier(
            IdentifierKind.TRACE_LINK, "REQ-ARCH-0008", "PLAN", "PLAN-ARCH-001"
        )
        mutation = deterministic_identifier(IdentifierKind.MUTATION, "REQ-ARCH-0008", "ADD", "PLAN")
        self.assertEqual(first, second)
        self.assertTrue(first.value.startswith("TRACE-"))
        self.assertTrue(mutation.value.startswith("MUT-"))

    def test_identifier_parser_recovers_kind(self) -> None:
        value = deterministic_identifier(
            IdentifierKind.TRANSITION, "task", "PP-TASK-000001", "READY"
        )
        parsed = DomainIdentifier.parse(value.value)
        self.assertEqual(parsed.kind, IdentifierKind.TRANSITION)

    def test_unknown_identifier_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DomainIdentifier.parse("not-an-identifier")
