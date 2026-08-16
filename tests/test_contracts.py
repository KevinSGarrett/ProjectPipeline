from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from project_pipeline.contracts import (
    ActionIntent,
    AdapterErrorCategory,
    AdapterErrorPayload,
    ApprovalState,
    CommandEnvelope,
    CommandResult,
    CommandStatus,
    RiskLevel,
    StateTransition,
    validate_schemas,
    write_schemas,
)

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_generated_schemas_are_deterministic_and_current(self) -> None:
        self.assertEqual(validate_schemas(ROOT), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = write_schemas(root)
            before = {name: (root / path).read_bytes() for name, path in first.items()}
            second = write_schemas(root)
            after = {name: (root / path).read_bytes() for name, path in second.items()}
            self.assertEqual(first, second)
            self.assertEqual(before, after)

    def test_command_requires_timezone_aware_timestamp(self) -> None:
        with self.assertRaises(ValidationError):
            CommandEnvelope(
                command_type="example.run",
                project_id="PROJECT-PIPELINE",
                actor_id="actor:one",
                correlation_id="corr:one",
                idempotency_key="example-key",
                issued_at_utc=datetime(2026, 8, 14, 12, 0, 0),
            )

    def test_action_intent_must_align_with_command_identity(self) -> None:
        intent = ActionIntent(
            actor_id="actor:one",
            authority="authority:local",
            target="repository",
            operation="repository.validate",
            risk=RiskLevel.LOW,
            idempotency_key="example-key",
            approval_state=ApprovalState.NOT_REQUIRED,
            correlation_id="corr:one",
        )
        with self.assertRaises(ValidationError):
            CommandEnvelope(
                command_type="repository.validate",
                project_id="PROJECT-PIPELINE",
                actor_id="actor:two",
                correlation_id="corr:one",
                idempotency_key="example-key",
                action_intent=intent,
            )

    def test_state_transition_rejects_noop(self) -> None:
        with self.assertRaises(ValidationError):
            StateTransition(
                entity_type="task",
                entity_id="task:one",
                previous_state="READY",
                next_state="READY",
                reason="No state change",
                command_id="command:one",
                correlation_id="corr:one",
            )

    def test_adapter_error_semantics_distinguish_retry_and_unknown_outcome(self) -> None:
        with self.assertRaises(ValidationError):
            AdapterErrorPayload(
                error_code="TIMEOUT",
                category=AdapterErrorCategory.TIMEOUT,
                message="Timed out",
                retryable=False,
                provider="provider:one",
                operation="operation.run",
                correlation_id="corr:one",
            )
        payload = AdapterErrorPayload(
            error_code="UNKNOWN_RESULT",
            category=AdapterErrorCategory.UNKNOWN_OUTCOME,
            message="The remote result is unknown",
            retryable=True,
            unknown_outcome=True,
            provider="provider:one",
            operation="operation.run",
            correlation_id="corr:one",
        )
        self.assertEqual(payload.category, AdapterErrorCategory.UNKNOWN_OUTCOME)

    def test_command_result_requires_error_for_failed_or_unknown_status(self) -> None:
        with self.assertRaises(ValidationError):
            CommandResult(
                command_id="command:one",
                command_type="example.run",
                project_id="PROJECT-PIPELINE",
                correlation_id="corr:one",
                idempotency_key="example-key",
                status=CommandStatus.FAILED,
            )
