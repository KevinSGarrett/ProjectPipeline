from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from project_pipeline.command_center.desktop_session import (
    DesktopBindError,
    DesktopSessionError,
    EphemeralSessionIssuer,
    scan_secret_residue,
    validate_bind_host,
)
from project_pipeline.command_center.live_server import (
    LiveCommandCenterServer,
    create_live_command_center_app,
)

ROOT = Path(__file__).resolve().parents[1]


def test_bind_policy_rejects_nonloopback_and_secret_persistence() -> None:
    assert validate_bind_host("localhost") == "127.0.0.1"
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    with pytest.raises(DesktopBindError, match="loopback-only"):
        validate_bind_host("0.0.0.0")
    with pytest.raises(DesktopBindError, match="loopback-only"):
        validate_bind_host("192.168.1.10")


def test_bootstrap_is_single_use_and_identity_bound(tmp_path: Path) -> None:
    issuer = EphemeralSessionIssuer(os_identity="desktop-operator")
    handshake = issuer.write_handshake(tmp_path / "handshake.json", url="http://127.0.0.1:8765")
    payload = json.loads(handshake.read_text(encoding="utf-8"))
    grant = issuer.redeem(
        payload["nonce"],
        peer_host="127.0.0.1",
        os_identity="desktop-operator",
    )
    assert issuer.authenticate(grant.token) == "actor:os:desktop-operator"
    assert not handshake.exists()
    with pytest.raises(DesktopSessionError, match="already redeemed"):
        issuer.redeem(payload["nonce"], peer_host="127.0.0.1", os_identity="desktop-operator")


def test_bootstrap_rejects_remote_peer_and_identity_mismatch() -> None:
    issuer = EphemeralSessionIssuer(os_identity="desktop-operator")
    with pytest.raises(DesktopSessionError, match="loopback-only"):
        issuer.redeem(issuer.bootstrap_nonce, peer_host="10.0.0.8", os_identity="desktop-operator")
    with pytest.raises(DesktopSessionError, match="os identity mismatch"):
        issuer.redeem(issuer.bootstrap_nonce, peer_host="127.0.0.1", os_identity="other")


def test_stale_and_revoked_tokens_are_rejected() -> None:
    issuer = EphemeralSessionIssuer(os_identity="desktop-operator")
    grant = issuer.redeem(
        issuer.bootstrap_nonce, peer_host="127.0.0.1", os_identity="desktop-operator"
    )
    issuer.revoke(grant.token)
    assert issuer.authenticate(grant.token) is None
    issuer = EphemeralSessionIssuer(os_identity="desktop-operator")
    grant = issuer.redeem(
        issuer.bootstrap_nonce, peer_host="127.0.0.1", os_identity="desktop-operator"
    )
    issuer.expire_all()
    assert issuer.authenticate(grant.token) is None


def test_live_preview_html_does_not_embed_token() -> None:
    app, _broker, issuer = create_live_command_center_app(ROOT, token="secret-token")
    html = TestClient(app).get("/").text
    assert "secret-token" not in html
    assert "CC_LIVE_TOKEN=" not in html
    assert issuer.authenticate("secret-token") == "actor:command-center"


def test_loopback_bootstrap_http_and_residue_scan(tmp_path: Path) -> None:
    handshake = tmp_path / "handshake.json"
    server = LiveCommandCenterServer(ROOT, handshake_path=handshake)
    url = server.start()
    try:
        payload = json.loads(handshake.read_text(encoding="utf-8"))
        request = urllib.request.Request(
            f"{url}/api/v1/command-center/session/bootstrap",
            data=json.dumps(
                {"nonce": payload["nonce"], "os_identity": server.issuer.os_identity}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        assert body["persist_secrets"] is False
        assert server.issuer.authenticate(body["token"])
        assert not handshake.exists()
        log = tmp_path / "server.log"
        log.write_text("started without secrets\n", encoding="utf-8")
        assert scan_secret_residue([log], forbidden_values=(body["token"], payload["nonce"])) == []
    finally:
        server.stop()
