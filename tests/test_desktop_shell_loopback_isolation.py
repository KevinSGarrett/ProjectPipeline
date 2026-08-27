from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_shell_reserves_and_verifies_its_own_loopback_endpoint() -> None:
    source = (ROOT / "apps" / "desktop_shell" / "src-tauri" / "src" / "main.rs").read_text(
        encoding="utf-8"
    )

    assert 'TcpListener::bind(("127.0.0.1", 0))' in source
    assert "fn handshake_port(handshake: &Handshake)" in source
    assert "handshake_port(&handshake)? == port && loopback_open(port)" in source
    assert "DEFAULT_PORT" not in source


def test_desktop_csp_allows_only_loopback_dynamic_ports() -> None:
    config = json.loads(
        (ROOT / "apps" / "desktop_shell" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    csp = config["app"]["security"]["csp"]

    assert "http://127.0.0.1:*" in csp
    assert "ws://127.0.0.1:*" in csp
    assert "http://*" not in csp
    assert "https://*" not in csp
