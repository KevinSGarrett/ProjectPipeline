from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from project_pipeline.infra.boundaries import (
    destroy_ephemeral,
    evaluate_capacity,
    evaluate_emulation,
    evaluate_overlay,
    ingest_event,
    provision_ephemeral,
    run_infra_action,
)


def test_overlay_rejects_unauthenticated_and_public_exposure() -> None:
    decision = evaluate_overlay(
        [
            {
                "peer_id": "cpu-01",
                "endpoint": "127.0.0.1:7100",
                "authenticated": True,
                "exposure": "loopback",
            },
            {
                "peer_id": "public",
                "endpoint": "0.0.0.0:80",
                "authenticated": True,
                "exposure": "public",
            },
        ]
    )
    assert decision.ok is False
    assert "public" in decision.rejected
    assert decision.peers[0].peer_id == "cpu-01"
    ipv6 = evaluate_overlay(
        [
            {
                "peer_id": "v6",
                "endpoint": "[::]:80",
                "authenticated": True,
                "exposure": "loopback",
            }
        ]
    )
    assert ipv6.ok is False
    assert "v6" in ipv6.rejected


def test_ephemeral_provision_is_idempotent_and_destroyed(tmp_path: Path) -> None:
    first = provision_ephemeral(tmp_path, "database", "db-1")
    second = provision_ephemeral(tmp_path, "database", "db-1")
    assert first.provisioned is True
    assert second.receipt_id == first.receipt_id
    assert (tmp_path / ".local/state/infra_ephemeral/db-1/ephemeral.sqlite3").is_file()
    try:
        provision_ephemeral(tmp_path, "queue", "db-1")
        raise AssertionError("kind mismatch must fail closed")
    except ValueError as error:
        assert "already provisioned" in str(error)
    destroyed = destroy_ephemeral(tmp_path, "db-1", "database")
    assert destroyed.destroyed is True
    assert not (tmp_path / ".local/state/infra_ephemeral/db-1").exists()


def test_emulation_cannot_substitute_for_live() -> None:
    decision = evaluate_emulation(enabled=True, claim_live=True)
    assert decision.substitutes_for_live is False
    assert decision.enabled is True


def test_ingress_authenticates_dedupes_and_never_grants_control(tmp_path: Path) -> None:
    store = tmp_path / "events.jsonl"
    payload = b'{"action":"opened"}'
    secret = b"shared-secret"
    signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    first = ingest_event(
        store,
        payload=payload,
        secret=secret,
        signature=signature,
        source="github",
        event_id="evt-1",
    )
    second = ingest_event(
        store,
        payload=payload,
        secret=secret,
        signature=signature,
        source="github",
        event_id="evt-1",
    )
    forged = ingest_event(
        store,
        payload=payload,
        secret=secret,
        signature="0" * 64,
        source="github",
        event_id="evt-2",
    )
    assert first.accepted is True
    assert first.delivered_to_director is True
    assert first.grants_control_authority is False
    assert second.deduplicated is True
    assert forged.accepted is False
    empty = ingest_event(
        store,
        payload=payload,
        secret=secret,
        signature=signature,
        source="github",
        event_id="",
    )
    assert empty.accepted is False


def test_capacity_denies_missing_checks_and_live_spend() -> None:
    denied = evaluate_capacity({"capability_need": True})
    assert denied.approved is False
    assert "spend_lease" in denied.missing_checks
    spend = evaluate_capacity(
        {
            "capability_need": True,
            "spend_lease": True,
            "quota": True,
            "security": True,
            "environment": True,
            "return_protocol": True,
            "live_spend": True,
        }
    )
    assert spend.approved is False
    accepted = evaluate_capacity(
        {
            "capability_need": True,
            "spend_lease": True,
            "quota": True,
            "security": True,
            "environment": True,
            "return_protocol": True,
        }
    )
    assert accepted.approved is True
    assert accepted.live_spend_authorized is False


def test_cli_status_is_local_and_machine_readable(tmp_path: Path) -> None:
    payload = run_infra_action(tmp_path, "status", payload={"emulation_enabled": True})
    assert payload["paid_dependency_required"] is False
    assert payload["user_action_required"] is False
    assert payload["emulation"]["substitutes_for_live"] is False
