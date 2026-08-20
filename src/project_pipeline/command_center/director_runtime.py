"""Governed execution coordination used by the Persistent Autonomy Director.

This module acquires Scheduler fences, compiles Context Engine packs, and records
Autonomy Runtime operations. It does not mutate GitHub or Jira and does not
dispatch an ungoverned provider.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor
from project_pipeline.context_engine.service import ContextService
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPolicy,
    ContextSourceKind,
    ContextTrust,
    DelegationEnvelope,
    ProviderEgress,
)
from project_pipeline.domain.scheduler import AccessMode, ResourceClaim, ResourceType
from project_pipeline.scheduler.persistence import SchedulerStore

_ALLOWED_PROVIDERS = frozenset(
    {"local", "qualified-local", "provider:local", "deterministic-local"}
)


class DirectorRuntimeError(RuntimeError):
    """Fail-closed director runtime coordination error."""


def default_director_claims(task_id: str) -> tuple[ResourceClaim, ...]:
    return (
        ResourceClaim(
            resource_key=f"director:{task_id}",
            resource_type=ResourceType.PATH,
            access_mode=AccessMode.EXCLUSIVE,
            purpose="director execution fence",
        ),
    )


class DirectorRuntime:
    """Compose Scheduler, Context Engine, and PersistentSupervisor for one decision."""

    def __init__(self, root: Path, database: Path) -> None:
        self.root = root.resolve()
        self.database = Path(database)

    def acquire(
        self,
        *,
        task_id: str,
        holder_id: str,
        claims: tuple[ResourceClaim, ...],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        with SchedulerStore(self.database, self.root) as store:
            bundle = store.acquire_bundle(
                task_id=task_id,
                holder_id=holder_id,
                claims=claims,
                ttl_seconds=900,
                now=now,
            )
        return {
            "acquired": bundle.acquired,
            "reasons": list(bundle.reasons),
            "leases": [
                {
                    "lease_id": lease.lease_id,
                    "holder_id": lease.holder_id,
                    "fencing_token": lease.fencing_token,
                    "resource_key": lease.claim.resource_key,
                }
                for lease in bundle.leases
            ],
        }

    def release(self, leases: list[dict[str, Any]], *, now: datetime | None = None) -> None:
        if not leases:
            return
        with SchedulerStore(self.database, self.root) as store:
            for lease in leases:
                store.release_lease(
                    str(lease["lease_id"]),
                    holder_id=str(lease["holder_id"]),
                    fencing_token=int(lease["fencing_token"]),
                    now=now,
                )

    def compile_context(
        self,
        *,
        task_id: str,
        decision_id: str,
        control_fingerprint: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        observed = now or datetime.now(UTC)
        envelope = DelegationEnvelope.create(
            objective=f"Continue Control-selected work {task_id}",
            return_protocol="typed director execution receipt",
            required_context_keys=("control_fingerprint", "decision_id"),
            scope=(task_id,),
            exclusions=("ungoverned-external-mutation", "raw-chat-mutation"),
        )
        candidates = (
            ContextCandidate(
                context_key="control_fingerprint",
                kind=ContextSourceKind.POLICY,
                content=control_fingerprint,
                revision_id=control_fingerprint[:32],
                observed_at_utc=observed,
                trust=ContextTrust.GOVERNING,
            ),
            ContextCandidate(
                context_key="decision_id",
                kind=ContextSourceKind.DECISION,
                content=decision_id,
                revision_id=decision_id,
                observed_at_utc=observed,
                trust=ContextTrust.AUTHORITATIVE,
            ),
        )
        policy = ContextPolicy(policy_version="CTX-POLICY-1.0")
        artifact_root = self.root / ".local" / "artifacts" / "director-context"
        with ContextService(
            root=self.root, database=self.database, artifact_root=artifact_root
        ) as service:
            pack = service.compile(
                envelope,
                candidates,
                policy,
                provider_egress=ProviderEgress.LOCAL_ONLY,
            )
        return {
            "pack_id": pack.pack_id,
            "delegation_id": pack.delegation_id,
            "item_count": len(pack.items),
        }

    def persist_operation(
        self,
        *,
        task_id: str,
        decision_id: str,
        fence_token: str,
        context_identity: str,
        provider: str,
        input_fingerprint: str,
    ) -> str:
        supervisor = PersistentSupervisor(self.database, self.root)
        try:
            operation_id = supervisor.start_operation(
                task_id=task_id,
                input_fingerprint=input_fingerprint,
                worker_id=f"director:{provider}",
                base_branch="main",
                worktree_path=str(self.root),
                lease_fence=fence_token,
                idempotency_key=f"director:{decision_id}:{task_id}",
                payload={
                    "decision_id": decision_id,
                    "context_identity": context_identity,
                    "provider": provider,
                    "external_mutation": "GOVERNED_ADAPTERS_ONLY",
                },
            )
            supervisor.mark_dispatched(operation_id)
            return operation_id
        finally:
            supervisor.close()

    def recover_unknown(
        self,
        operation_id: str,
        *,
        applied: bool,
    ) -> None:
        supervisor = PersistentSupervisor(self.database, self.root)
        try:
            supervisor.mark_unknown_outcome(operation_id)
            supervisor.reconcile_unknown_outcome(operation_id, applied=applied)
        finally:
            supervisor.close()


def qualify_local_provider(provider: str) -> str:
    if provider not in _ALLOWED_PROVIDERS:
        raise DirectorRuntimeError(f"provider {provider} is not admitted for director coordination")
    return provider
