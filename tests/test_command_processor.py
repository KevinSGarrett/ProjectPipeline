from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_pipeline.contracts import CommandEnvelope, CommandResult, CommandStatus
from project_pipeline.core import CommandProcessor, IdempotencyConflictError, LocalCommandJournal
from project_pipeline.core.command_bus import UnknownCommandError


class CommandProcessorTests(unittest.TestCase):
    @staticmethod
    def envelope(**updates: object) -> CommandEnvelope:
        values: dict[str, object] = {
            "command_type": "example.run",
            "project_id": "PROJECT-PIPELINE",
            "actor_id": "actor:one",
            "correlation_id": "corr:one",
            "idempotency_key": "example-key",
            "payload": {"value": 1},
        }
        values.update(updates)
        return CommandEnvelope(**values)

    @staticmethod
    def result(envelope: CommandEnvelope, **updates: object) -> CommandResult:
        values: dict[str, object] = {
            "command_id": envelope.command_id,
            "command_type": envelope.command_type,
            "project_id": envelope.project_id,
            "correlation_id": envelope.correlation_id,
            "idempotency_key": envelope.idempotency_key,
            "status": CommandStatus.SUCCEEDED,
            "output": {"value": 2},
        }
        values.update(updates)
        return CommandResult(**values)

    def test_second_execution_replays_without_calling_handler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = CommandProcessor(LocalCommandJournal(Path(directory)))
            calls: list[str] = []

            def handler(envelope: CommandEnvelope) -> CommandResult:
                calls.append(envelope.command_id)
                return self.result(envelope)

            processor.register("example.run", handler)
            envelope = self.envelope()
            first = processor.execute(envelope)
            second = processor.execute(envelope)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first.output, second.output)

    def test_reusing_key_for_different_semantics_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = CommandProcessor(LocalCommandJournal(Path(directory)))
            processor.register("example.run", lambda envelope: self.result(envelope))
            processor.execute(self.envelope())
            with self.assertRaises(IdempotencyConflictError):
                processor.execute(self.envelope(payload={"value": 99}))

    def test_result_identity_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = CommandProcessor(LocalCommandJournal(Path(directory)))
            processor.register(
                "example.run",
                lambda envelope: self.result(envelope, correlation_id="corr:different"),
            )
            with self.assertRaises(ValueError):
                processor.execute(self.envelope())

    def test_unknown_command_is_rejected_and_duplicate_handler_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = CommandProcessor(LocalCommandJournal(Path(directory)))
            with self.assertRaises(UnknownCommandError):
                processor.execute(self.envelope())
            processor.register("example.run", lambda envelope: self.result(envelope))
            with self.assertRaises(ValueError):
                processor.register("example.run", lambda envelope: self.result(envelope))
