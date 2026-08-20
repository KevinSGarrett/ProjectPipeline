from __future__ import annotations

import contextlib
import getpass
import json
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
HANDSHAKE_SCHEMA_VERSION = "1.0.0"
SESSION_ACTOR_PREFIX = "actor:os"


class DesktopBindError(ValueError):
    """Raised when a Command Center bind host is rejected by ADR-0028."""


class DesktopSessionError(PermissionError):
    """Raised when ephemeral session bootstrap or authentication fails closed."""


@dataclass(frozen=True, slots=True)
class DesktopBindPolicy:
    allow_nonloopback: bool = False
    require_tls_for_nonloopback: bool = True
    require_auth_for_nonloopback: bool = True
    persist_secrets: bool = False
    decision_id: str = "ADR-0028"


@dataclass(frozen=True, slots=True)
class SessionGrant:
    token: str
    actor_id: str
    os_identity: str
    session_id: str
    expires_at_utc: datetime

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "os_identity": self.os_identity,
            "session_id": self.session_id,
            "expires_at_utc": self.expires_at_utc.isoformat(),
            "persist_secrets": False,
        }


@dataclass
class _SessionRecord:
    grant: SessionGrant
    revoked: bool = False


def current_os_identity() -> str:
    for key in ("USERNAME", "USER"):
        value = os.environ.get(key)
        if value:
            return value
    return getpass.getuser()


def is_loopback_host(host: str) -> bool:
    return host in LOOPBACK_HOSTS


def validate_bind_host(host: str, policy: DesktopBindPolicy | None = None) -> str:
    policy = policy or DesktopBindPolicy()
    if policy.persist_secrets:
        raise DesktopBindError("Command Center must not persist bootstrap or session secrets")
    if is_loopback_host(host):
        return "127.0.0.1" if host == "localhost" else host
    if not policy.allow_nonloopback:
        raise DesktopBindError("Command Center live server is loopback-only")
    if not policy.require_tls_for_nonloopback or not policy.require_auth_for_nonloopback:
        raise DesktopBindError("non-loopback Command Center bind requires TLS and authentication")
    raise DesktopBindError(
        "non-loopback Command Center bind is not admitted until the authenticated TLS profile exists"
    )


def policy_from_mapping(payload: dict[str, Any] | None) -> DesktopBindPolicy:
    desktop = (payload or {}).get("desktop_auth") if isinstance(payload, dict) else None
    desktop = desktop if isinstance(desktop, dict) else {}
    return DesktopBindPolicy(
        allow_nonloopback=bool(desktop.get("allow_nonloopback", False)),
        require_tls_for_nonloopback=bool(desktop.get("require_tls_for_nonloopback", True)),
        require_auth_for_nonloopback=bool(desktop.get("require_auth_for_nonloopback", True)),
        persist_secrets=bool(desktop.get("persist_secrets", False)),
        decision_id=str(desktop.get("decision_id") or "ADR-0028"),
    )


class EphemeralSessionIssuer:
    def __init__(
        self,
        *,
        os_identity: str | None = None,
        ttl_seconds: int = 3600,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("session ttl must be positive")
        self.os_identity = os_identity or current_os_identity()
        self.ttl_seconds = ttl_seconds
        self.bootstrap_nonce = secrets.token_urlsafe(32)
        self._nonce_used = False
        self._sessions: dict[str, _SessionRecord] = {}
        self._handshake_path: Path | None = None

    def seed_static_token(
        self,
        token: str,
        *,
        actor_id: str = "actor:command-center",
    ) -> SessionGrant:
        if not token:
            raise DesktopSessionError("static session token is empty")
        grant = SessionGrant(
            token=token,
            actor_id=actor_id,
            os_identity=self.os_identity,
            session_id=f"session:{uuid4().hex}",
            expires_at_utc=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        )
        self._sessions[token] = _SessionRecord(grant=grant)
        return grant

    def write_handshake(self, path: Path, *, url: str) -> Path:
        path = path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": HANDSHAKE_SCHEMA_VERSION,
            "nonce": self.bootstrap_nonce,
            "url": url,
            "os_identity": self.os_identity,
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with contextlib.suppress(OSError):
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self._handshake_path = path
        return path

    def redeem(
        self,
        nonce: str,
        *,
        peer_host: str,
        os_identity: str,
    ) -> SessionGrant:
        if not is_loopback_host(peer_host):
            raise DesktopSessionError("bootstrap is loopback-only")
        if self._nonce_used:
            raise DesktopSessionError("bootstrap nonce already redeemed")
        if not nonce or not secrets.compare_digest(nonce, self.bootstrap_nonce):
            raise DesktopSessionError("invalid bootstrap nonce")
        if os_identity != self.os_identity:
            raise DesktopSessionError("os identity mismatch")
        self._nonce_used = True
        self._unlink_handshake()
        token = secrets.token_urlsafe(32)
        grant = SessionGrant(
            token=token,
            actor_id=f"{SESSION_ACTOR_PREFIX}:{self.os_identity}",
            os_identity=self.os_identity,
            session_id=f"session:{uuid4().hex}",
            expires_at_utc=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        )
        self._sessions[token] = _SessionRecord(grant=grant)
        return grant

    def authenticate(self, token: str) -> str | None:
        record = self._sessions.get(token)
        if record is None or record.revoked:
            return None
        if record.grant.expires_at_utc <= datetime.now(UTC):
            return None
        return record.grant.actor_id

    def revoke(self, token: str) -> None:
        record = self._sessions.get(token)
        if record is not None:
            record.revoked = True

    def expire_all(self) -> None:
        past = datetime.now(UTC) - timedelta(seconds=1)
        for record in self._sessions.values():
            record.grant = SessionGrant(
                token=record.grant.token,
                actor_id=record.grant.actor_id,
                os_identity=record.grant.os_identity,
                session_id=record.grant.session_id,
                expires_at_utc=past,
            )

    def _unlink_handshake(self) -> None:
        path = self._handshake_path
        self._handshake_path = None
        if path is None:
            return
        try:
            path.unlink()
        except FileNotFoundError:
            return


def scan_secret_residue(
    paths: list[Path],
    *,
    forbidden_values: tuple[str, ...],
) -> list[str]:
    findings: list[str] = []
    needles = tuple(value for value in forbidden_values if value)
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle in text:
                findings.append(f"{path.as_posix()}: secret residue matched")
                break
    return findings
