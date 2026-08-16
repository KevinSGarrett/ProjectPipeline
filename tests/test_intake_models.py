from __future__ import annotations

import unittest
from datetime import datetime

from pydantic import ValidationError

from project_pipeline.domain import (
    BootstrapOutcome,
    BootstrapReceipt,
    GapCategory,
    GapSeverity,
    IdentifierKind,
    IntakeMode,
    ProjectGap,
    ProjectIntakeRequest,
    ProjectProfile,
    deterministic_identifier,
)


class IntakeModelTests(unittest.TestCase):
    def test_intake_request_resolves_stable_project_identity(self) -> None:
        request = ProjectIntakeRequest(
            mode=IntakeMode.NEW_PROJECT,
            project_name="Project—Example",
            target_root="/tmp/example",
            requested_profiles=(ProjectProfile.PYTHON_SERVICE,),
        )
        self.assertEqual(request.resolved_project_id(), "PROJECT-EXAMPLE")
        self.assertEqual(len(request.semantic_fingerprint()), 64)

    def test_intake_request_rejects_duplicate_profiles_and_unsafe_text(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectIntakeRequest(
                mode=IntakeMode.NEW_PROJECT,
                project_name="Example\nInjected",
                target_root="/tmp/example",
            )
        with self.assertRaises(ValidationError):
            ProjectIntakeRequest(
                mode=IntakeMode.NEW_PROJECT,
                project_name="Example",
                target_root="/tmp/example",
                requested_profiles=(
                    ProjectProfile.PYTHON_LIBRARY,
                    ProjectProfile.PYTHON_LIBRARY,
                ),
            )

    def test_gap_identity_supports_global_gaps_without_affected_paths(self) -> None:
        first = ProjectGap.create(
            category=GapCategory.GOVERNANCE,
            severity=GapSeverity.LOW,
            title="License decision required",
            description="No license is declared.",
            remediation="Request an owner-approved license decision.",
        )
        second = ProjectGap.create(
            category=GapCategory.GOVERNANCE,
            severity=GapSeverity.LOW,
            title="License decision required",
            description="No license is declared.",
            remediation="Request an owner-approved license decision.",
        )
        self.assertEqual(first.gap_id, second.gap_id)
        self.assertTrue(first.gap_id.startswith("GAP-"))

    def test_bootstrap_receipt_rejects_success_with_conflicts(self) -> None:
        bootstrap_id = str(
            deterministic_identifier(IdentifierKind.BOOTSTRAP, "compilation", "root", "plan")
        )
        compilation_id = str(
            deterministic_identifier(
                IdentifierKind.COMPILATION, "project", "request", "map", "gaps", "profile"
            )
        )
        with self.assertRaises(ValidationError):
            BootstrapReceipt(
                bootstrap_id=bootstrap_id,
                compilation_id=compilation_id,
                outcome=BootstrapOutcome.APPLIED,
                target_root="/tmp/example",
                conflict_paths=("README.md",),
                actor_id="actor:test",
                correlation_id="corr:test",
                recorded_at_utc=datetime.now().astimezone(),
            )
