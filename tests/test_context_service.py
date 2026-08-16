from datetime import UTC, datetime

from project_pipeline.context_engine.service import ContextService
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPolicy,
    ContextSourceKind,
    ContextTrust,
    DelegationEnvelope,
    ReceiptStatus,
)


def test_context_service_persists_pack_receipt_and_artifact(tmp_path, project_root):
    now = datetime.now(UTC)
    e = DelegationEnvelope.create(objective="x", return_protocol="y", required_context_keys=("a",))
    c = ContextCandidate(
        context_key="a",
        kind=ContextSourceKind.OTHER,
        content="hello",
        revision_id="1",
        observed_at_utc=now,
        trust=ContextTrust.AUTHORITATIVE,
    )
    p = ContextPolicy(policy_version="CTX-POLICY-1.0")
    with ContextService(
        root=project_root, database=tmp_path / "state.db", artifact_root=tmp_path / "artifacts"
    ) as s:
        pack = s.compile(e, (c,), p)
        assert s.store.get_pack(pack.pack_id) == pack
        receipt = s.receipt(pack_id=pack.pack_id, worker_id="w", status=ReceiptStatus.CONSUMED)
        assert s.store.get_receipt(receipt.receipt_id) == receipt
