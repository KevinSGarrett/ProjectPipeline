from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from project_pipeline.contracts import CommandEnvelope, CommandResult


class IdempotencyConflictError(RuntimeError):
    """Raised when one idempotency key is reused for different command semantics."""


class JournalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    semantic_fingerprint: str
    envelope: CommandEnvelope
    result: CommandResult


class LocalCommandJournal:
    """Atomic local command-result journal keyed by a hashed idempotency key."""

    def __init__(self, root: Path, *, create: bool = True) -> None:
        self.root = root.resolve()
        if create:
            self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key_digest(idempotency_key: str) -> str:
        return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()

    def _record_path(self, idempotency_key: str) -> Path:
        digest = self._key_digest(idempotency_key)
        return self.root / digest[:2] / f"{digest}.json"

    def get(self, envelope: CommandEnvelope) -> CommandResult | None:
        path = self._record_path(envelope.idempotency_key)
        if not path.is_file():
            return None
        record = JournalRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if record.semantic_fingerprint != envelope.semantic_fingerprint():
            raise IdempotencyConflictError(
                "idempotency key was already used for a different command"
            )
        return record.result.model_copy(update={"replayed": True})

    def store(self, envelope: CommandEnvelope, result: CommandResult) -> None:
        path = self._record_path(envelope.idempotency_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = JournalRecord(
            semantic_fingerprint=envelope.semantic_fingerprint(),
            envelope=envelope,
            result=result,
        )
        payload = record.model_dump_json(indent=2).encode("utf-8") + b"\n"
        if path.exists():
            self.get(envelope)
            return
        descriptor, temporary = tempfile.mkstemp(prefix=".command-", dir=path.parent)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                self.get(envelope)
            except OSError:
                if path.exists():
                    self.get(envelope)
                else:
                    os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
