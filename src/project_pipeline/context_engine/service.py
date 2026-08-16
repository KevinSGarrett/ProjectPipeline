from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.artifacts import LocalContentAddressedStore
from project_pipeline.context_engine.broker import ContextBroker
from project_pipeline.context_engine.compiler import ContextCompiler
from project_pipeline.context_engine.persistence import ContextStore
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPack,
    ContextPolicy,
    ContextReceipt,
    DelegationEnvelope,
    ProviderEgress,
    ReceiptStatus,
)


class ContextService:
    def __init__(self, *, root: Path, database: Path | str, artifact_root: Path | None = None):
        self.root = root.resolve()
        self.store = ContextStore(database, self.root)
        self.artifacts = LocalContentAddressedStore(
            (artifact_root or self.root / ".local/artifacts/context").resolve()
        )
        self.broker = ContextBroker()
        self.compiler = ContextCompiler()

    def __enter__(self):
        self.store.__enter__()
        return self

    def __exit__(self, *args):
        self.store.__exit__(*args)

    def compile(
        self,
        envelope: DelegationEnvelope,
        candidates: tuple[ContextCandidate, ...],
        policy: ContextPolicy,
        *,
        provider_egress: ProviderEgress = ProviderEgress.LOCAL_ONLY,
    ) -> ContextPack:
        selection = self.broker.select(envelope, candidates, policy)
        pack = self.compiler.compile(
            envelope, selection, candidates, policy, provider_egress=provider_egress
        )
        payload = json.dumps(
            pack.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        ref = self.artifacts.put(payload, "application/vnd.project-pipeline.context-pack+json")
        artifact_digest = ref.digest
        if not artifact_digest:
            raise RuntimeError("context artifact digest was not produced")
        self.store.save_delegation(envelope)
        self.store.save_pack(pack)
        return pack

    def receipt(
        self,
        *,
        pack_id: str,
        worker_id: str,
        status: ReceiptStatus,
        omissions: tuple[str, ...] = (),
        conflicts: tuple[str, ...] = (),
        requested: tuple[str, ...] = (),
    ) -> ContextReceipt:
        if self.store.get_pack(pack_id) is None:
            raise KeyError(f"unknown context pack: {pack_id}")
        receipt = ContextReceipt.create(
            pack_id=pack_id,
            worker_id=worker_id,
            status=status,
            omissions_detected=omissions,
            conflicts_encountered=conflicts,
            additional_context_requested=requested,
        )
        self.store.save_receipt(receipt)
        return receipt
