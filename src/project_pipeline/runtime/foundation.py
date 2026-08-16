from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from project_pipeline.artifacts import LocalContentAddressedStore
from project_pipeline.configuration import EffectiveConfiguration
from project_pipeline.contracts import (
    CommandEnvelope,
    CommandResult,
    CommandStatus,
    EventEnvelope,
    StateTransition,
)
from project_pipeline.core import CommandProcessor, LocalCommandJournal
from project_pipeline.observability import configure_logging


@dataclass(frozen=True, slots=True)
class FoundationSmokeReport:
    schema_version: str
    ok: bool
    command_id: str
    correlation_id: str
    first_status: str
    replay_status: str
    replayed: bool
    semantic_fingerprint: str
    artifact_digest: str
    artifact_verified: bool
    journal_root: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_foundation_smoke(
    root: Path,
    configuration: EffectiveConfiguration,
    *,
    actor_id: str = "local-operator",
    correlation_id: str = "corr:foundation-smoke",
) -> FoundationSmokeReport:
    settings = configuration.settings
    paths = settings.runtime_paths(root)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    logger = configure_logging(settings.logging)
    journal = LocalCommandJournal(paths["state_dir"] / "command-journal")
    artifacts = LocalContentAddressedStore(paths["artifact_dir"])
    processor = CommandProcessor(journal, logger)

    def handle(envelope: CommandEnvelope) -> CommandResult:
        transition = StateTransition(
            entity_type="runtime",
            entity_id=settings.project_id,
            previous_state="BOOTSTRAPPED",
            next_state="FOUNDATION_VERIFIED",
            reason="Typed command processing, event creation, idempotent replay, and artifact integrity succeeded.",
            command_id=envelope.command_id,
            correlation_id=envelope.correlation_id,
        )
        event = EventEnvelope(
            event_type="foundation.smoke.completed",
            project_id=settings.project_id,
            producer=settings.logging.service_name,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.command_id,
            actor_id=envelope.actor_id,
            aggregate_type="runtime",
            aggregate_id=settings.project_id,
            payload={
                "configuration_fingerprint": configuration.fingerprint(),
                "profile": settings.profile,
            },
        )
        return CommandResult(
            command_id=envelope.command_id,
            command_type=envelope.command_type,
            project_id=envelope.project_id,
            correlation_id=envelope.correlation_id,
            idempotency_key=envelope.idempotency_key,
            status=CommandStatus.SUCCEEDED,
            output={"verified": True},
            transitions=(transition,),
            events=(event,),
        )

    processor.register("foundation.smoke", handle)
    envelope = CommandEnvelope(
        command_type="foundation.smoke",
        project_id=settings.project_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        idempotency_key=f"foundation:{configuration.fingerprint()}",
        authority_scope=("local.foundation.verify",),
        dry_run=False,
        payload={"profile": settings.profile},
    )
    first = processor.execute(envelope)
    replay = processor.execute(envelope)
    payload = (
        json.dumps(
            {
                "command": envelope.model_dump(mode="json"),
                "result": first.model_dump(mode="json"),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )
    reference = artifacts.put(payload, "application/json")
    ok = (
        first.status is CommandStatus.SUCCEEDED
        and replay.status is CommandStatus.SUCCEEDED
        and replay.replayed
        and artifacts.verify(reference)
    )
    return FoundationSmokeReport(
        schema_version="1.0.0",
        ok=ok,
        command_id=envelope.command_id,
        correlation_id=envelope.correlation_id,
        first_status=first.status.value,
        replay_status=replay.status.value,
        replayed=replay.replayed,
        semantic_fingerprint=envelope.semantic_fingerprint(),
        artifact_digest=reference.digest,
        artifact_verified=artifacts.verify(reference),
        journal_root=str(journal.root),
    )
