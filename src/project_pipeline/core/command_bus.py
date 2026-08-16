from __future__ import annotations

import logging
from collections.abc import Callable

from project_pipeline.contracts import CommandEnvelope, CommandResult
from project_pipeline.core.journal import LocalCommandJournal
from project_pipeline.observability import correlation_scope, log_event

CommandHandler = Callable[[CommandEnvelope], CommandResult]


class UnknownCommandError(LookupError):
    """Raised when no handler is registered for a command type."""


class CommandProcessor:
    def __init__(self, journal: LocalCommandJournal, logger: logging.Logger | None = None) -> None:
        self.journal = journal
        self.logger = logger or logging.getLogger("project-pipeline.command-processor")
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, command_type: str, handler: CommandHandler) -> None:
        if command_type in self._handlers:
            raise ValueError(f"handler already registered: {command_type}")
        self._handlers[command_type] = handler

    def execute(self, envelope: CommandEnvelope) -> CommandResult:
        replay = self.journal.get(envelope)
        if replay is not None:
            with correlation_scope(
                project_id=envelope.project_id,
                actor_id=envelope.actor_id,
                correlation_id=envelope.correlation_id,
                causation_id=envelope.command_id,
            ):
                log_event(
                    self.logger,
                    logging.INFO,
                    "command_replayed",
                    command_id=envelope.command_id,
                    command_type=envelope.command_type,
                    idempotency_key_digest=envelope.semantic_fingerprint(),
                )
            return replay
        handler = self._handlers.get(envelope.command_type)
        if handler is None:
            raise UnknownCommandError(envelope.command_type)
        with correlation_scope(
            project_id=envelope.project_id,
            actor_id=envelope.actor_id,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.command_id,
        ):
            log_event(
                self.logger,
                logging.INFO,
                "command_started",
                command_id=envelope.command_id,
                command_type=envelope.command_type,
                dry_run=envelope.dry_run,
            )
            result = handler(envelope)
            self._validate_result(envelope, result)
            self.journal.store(envelope, result)
            log_event(
                self.logger,
                logging.INFO,
                "command_completed",
                command_id=envelope.command_id,
                command_type=envelope.command_type,
                status=result.status.value,
            )
            return result

    @staticmethod
    def _validate_result(envelope: CommandEnvelope, result: CommandResult) -> None:
        expected = (
            envelope.command_id,
            envelope.command_type,
            envelope.project_id,
            envelope.correlation_id,
            envelope.idempotency_key,
        )
        observed = (
            result.command_id,
            result.command_type,
            result.project_id,
            result.correlation_id,
            result.idempotency_key,
        )
        if observed != expected:
            raise ValueError("command result does not match command envelope")
