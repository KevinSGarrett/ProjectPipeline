from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from project_pipeline.domain.base import DomainModel

ALLOWED_EXPOSURES = frozenset({"loopback", "private-overlay"})
REQUIRED_CAPACITY_CHECKS = (
    "capability_need",
    "spend_lease",
    "quota",
    "security",
    "environment",
    "return_protocol",
)


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


class OverlayPeer(DomainModel):
    peer_id: str
    endpoint: str
    authenticated: bool
    exposure: str


class OverlayDecision(DomainModel):
    ok: bool
    overlay: Literal["private-authenticated"]
    peers: tuple[OverlayPeer, ...]
    rejected: tuple[str, ...]
    user_action_required: Literal[False] = False


class EphemeralResource(DomainModel):
    resource_id: str
    kind: str
    path: str
    provisioned: bool
    destroyed: bool
    receipt_id: str


class EmulationDecision(DomainModel):
    enabled: bool
    substitutes_for_live: Literal[False] = False
    provider: str
    reason: str
    user_action_required: Literal[False] = False


class IngressEvent(DomainModel):
    event_id: str
    source: str
    accepted: bool
    deduplicated: bool
    delivered_to_director: bool
    grants_control_authority: Literal[False] = False
    reason: str


class CapacityDecision(DomainModel):
    approved: bool
    live_spend_authorized: Literal[False] = False
    missing_checks: tuple[str, ...]
    reason: str
    user_action_required: Literal[False] = False


def evaluate_overlay(peers: list[dict[str, Any]]) -> OverlayDecision:
    accepted: list[OverlayPeer] = []
    rejected: list[str] = []
    for raw in peers:
        peer_id = str(raw.get("peer_id") or "")
        endpoint = str(raw.get("endpoint") or "")
        authenticated = bool(raw.get("authenticated"))
        exposure = str(raw.get("exposure") or "")
        if not peer_id or not authenticated or exposure not in ALLOWED_EXPOSURES:
            rejected.append(peer_id or endpoint or "unknown-peer")
            continue
        if endpoint.startswith("0.0.0.0") or exposure == "public":
            rejected.append(peer_id)
            continue
        accepted.append(
            OverlayPeer(
                peer_id=peer_id,
                endpoint=endpoint,
                authenticated=True,
                exposure=exposure,
            )
        )
    return OverlayDecision(
        ok=bool(accepted) and not rejected,
        overlay="private-authenticated",
        peers=tuple(accepted),
        rejected=tuple(rejected),
    )


def provision_ephemeral(root: Path, kind: str, resource_id: str) -> EphemeralResource:
    if not kind or not resource_id:
        raise ValueError("ephemeral provision requires kind and resource_id")
    base = root / ".local" / "state" / "infra_ephemeral" / resource_id
    if base.exists():
        return EphemeralResource(
            resource_id=resource_id,
            kind=kind,
            path=base.as_posix(),
            provisioned=True,
            destroyed=False,
            receipt_id=_digest("provision", resource_id, kind),
        )
    base.mkdir(parents=True, exist_ok=True)
    if kind == "database":
        sqlite3.connect(base / "ephemeral.sqlite3").close()
    elif kind == "queue":
        (base / "queue.jsonl").write_text("", encoding="utf-8")
    elif kind in {"browser", "service"}:
        (base / "ready").write_text(kind, encoding="utf-8")
    else:
        raise ValueError(f"unsupported ephemeral kind: {kind}")
    return EphemeralResource(
        resource_id=resource_id,
        kind=kind,
        path=base.as_posix(),
        provisioned=True,
        destroyed=False,
        receipt_id=_digest("provision", resource_id, kind),
    )


def destroy_ephemeral(root: Path, resource_id: str, kind: str) -> EphemeralResource:
    base = root / ".local" / "state" / "infra_ephemeral" / resource_id
    if base.exists():
        shutil.rmtree(base)
    return EphemeralResource(
        resource_id=resource_id,
        kind=kind,
        path=base.as_posix(),
        provisioned=False,
        destroyed=True,
        receipt_id=_digest("destroy", resource_id, kind),
    )


def evaluate_emulation(
    *, enabled: bool, claim_live: bool, provider: str = "local-emulator"
) -> EmulationDecision:
    if claim_live:
        return EmulationDecision(
            enabled=enabled,
            substitutes_for_live=False,
            provider=provider,
            reason="local cloud emulation cannot substitute for required live validation",
        )
    return EmulationDecision(
        enabled=enabled,
        provider=provider,
        reason="optional local emulator for inexpensive development tests only",
    )


def ingest_event(
    store: Path,
    *,
    payload: bytes,
    secret: bytes,
    signature: str,
    source: str,
    event_id: str,
) -> IngressEvent:
    store.parent.mkdir(parents=True, exist_ok=True)
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        return IngressEvent(
            event_id=event_id,
            source=source,
            accepted=False,
            deduplicated=False,
            delivered_to_director=False,
            reason="authenticity validation failed",
        )
    existing = set()
    if store.is_file():
        existing = {
            json.loads(line)["event_id"]
            for line in store.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    if event_id in existing:
        return IngressEvent(
            event_id=event_id,
            source=source,
            accepted=True,
            deduplicated=True,
            delivered_to_director=False,
            reason="duplicate event retained without redelivery",
        )
    record = {
        "event_id": event_id,
        "source": source,
        "accepted_at_utc": _now().isoformat(),
        "director_delivery": "advisory",
        "grants_control_authority": False,
    }
    with store.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return IngressEvent(
        event_id=event_id,
        source=source,
        accepted=True,
        deduplicated=False,
        delivered_to_director=True,
        reason="authenticated event enqueued for the active director without control authority",
    )


def evaluate_capacity(request: dict[str, Any]) -> CapacityDecision:
    missing = [item for item in REQUIRED_CAPACITY_CHECKS if not request.get(item)]
    if missing:
        return CapacityDecision(
            approved=False,
            missing_checks=tuple(missing),
            reason="cloud burst denied until every required check is present",
        )
    if request.get("live_spend"):
        return CapacityDecision(
            approved=False,
            missing_checks=(),
            reason="live spend is not authorized merely to prove the interface",
        )
    return CapacityDecision(
        approved=True,
        missing_checks=(),
        reason="local deterministic capacity request accepted; no live spend",
    )


def evaluate_infra_boundaries(root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    overlay = evaluate_overlay(list(body.get("peers") or []))
    emulation = evaluate_emulation(
        enabled=bool(body.get("emulation_enabled")),
        claim_live=bool(body.get("emulation_claims_live")),
    )
    capacity = evaluate_capacity(dict(body.get("capacity") or {}))
    return {
        "overlay": overlay.model_dump(mode="json"),
        "emulation": emulation.model_dump(mode="json"),
        "capacity": capacity.model_dump(mode="json"),
        "paid_dependency_required": False,
        "user_action_required": False,
        "root": str(root),
    }


def run_infra_action(
    root: Path,
    action: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    body = payload or {}
    if action == "status":
        return evaluate_infra_boundaries(root, body)
    if action == "overlay":
        return evaluate_overlay(list(body.get("peers") or [])).model_dump(mode="json")
    if action == "provision":
        return provision_ephemeral(
            root, str(body.get("kind") or ""), str(body.get("resource_id") or "")
        ).model_dump(mode="json")
    if action == "destroy":
        return destroy_ephemeral(
            root, str(body.get("resource_id") or ""), str(body.get("kind") or "")
        ).model_dump(mode="json")
    if action == "emulation":
        return evaluate_emulation(
            enabled=bool(body.get("enabled")),
            claim_live=bool(body.get("claim_live")),
            provider=str(body.get("provider") or "local-emulator"),
        ).model_dump(mode="json")
    if action == "ingress":
        store = root / ".local" / "state" / "infra_ingress" / "events.jsonl"
        return ingest_event(
            store,
            payload=str(body.get("payload") or "").encode("utf-8"),
            secret=str(body.get("secret") or "").encode("utf-8"),
            signature=str(body.get("signature") or ""),
            source=str(body.get("source") or "github"),
            event_id=str(body.get("event_id") or ""),
        ).model_dump(mode="json")
    if action == "capacity":
        return evaluate_capacity(body).model_dump(mode="json")
    raise ValueError(f"unsupported infra-boundaries action: {action}")
