from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SECRET_SHAPED = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"
    r"|sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}"
)
SENSITIVE_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)$")
REQUIRED_FIELDS = (
    "artifact_id",
    "sbom_sha256",
    "license_result_sha256",
    "vulnerability_result_sha256",
    "provenance_sha256",
    "signer_identity_id",
    "approval_id",
    "build_id",
    "release_decision",
)
MAX_QUERY = 100


def _now() -> datetime:
    return datetime.now(UTC)


def contains_secret_shaped(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            SENSITIVE_KEY.search(str(key)) or contains_secret_shaped(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret_shaped(item) for item in value)
    return isinstance(value, str) and bool(SECRET_SHAPED.search(value))


def artifact_digest(payload: dict[str, Any]) -> str:
    bound = {field: payload.get(field) for field in REQUIRED_FIELDS}
    encoded = json.dumps(bound, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ArtifactBindingStore:
    """Immutable artifact-binding ledger with fail-closed replay and revocation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS artifact_bindings (
                    binding_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(artifact_id, digest)
                );
                CREATE TABLE IF NOT EXISTS artifact_binding_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    binding_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        self._db.close()

    def bind(self, payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        if contains_secret_shaped(payload):
            raise ValueError("secret-shaped artifact binding is denied")
        missing = [field for field in REQUIRED_FIELDS if not payload.get(field)]
        if missing:
            raise ValueError(f"missing binding fields: {missing}")
        expires = payload.get("expires_at_utc")
        observed = now or _now()
        if expires:
            expiry = datetime.fromisoformat(str(expires))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry <= observed:
                raise ValueError("expired identity, policy, or approval")
        digest = artifact_digest(payload)
        binding_id = f"BIND-{digest[:16]}"
        encoded = json.dumps(payload, sort_keys=True)
        with self._db:
            existing = self._db.execute(
                "SELECT * FROM artifact_bindings WHERE artifact_id = ?",
                (payload["artifact_id"],),
            ).fetchone()
            if existing is not None:
                if str(existing["digest"]) == digest:
                    return dict(existing) | {"replayed": True}
                raise ValueError("conflicting artifact binding replay")
            self._db.execute(
                """
                INSERT INTO artifact_bindings (
                    binding_id, artifact_id, digest, payload_json, created_at_utc, revoked
                ) VALUES (?, ?, ?, ?, ?, 0)
                """,
                (
                    binding_id,
                    payload["artifact_id"],
                    digest,
                    encoded,
                    observed.isoformat(),
                ),
            )
            self._db.execute(
                """
                INSERT INTO artifact_binding_audit (binding_id, action, digest, created_at_utc)
                VALUES (?, 'BIND', ?, ?)
                """,
                (binding_id, digest, observed.isoformat()),
            )
        return {
            "binding_id": binding_id,
            "artifact_id": payload["artifact_id"],
            "digest": digest,
            "revoked": 0,
            "replayed": False,
        }

    def revoke(self, binding_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        observed = now or _now()
        with self._db:
            row = self._db.execute(
                "SELECT * FROM artifact_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown binding: {binding_id}")
            self._db.execute(
                "UPDATE artifact_bindings SET revoked = 1 WHERE binding_id = ?",
                (binding_id,),
            )
            self._db.execute(
                """
                INSERT INTO artifact_binding_audit (binding_id, action, digest, created_at_utc)
                VALUES (?, 'REVOKE', ?, ?)
                """,
                (binding_id, str(row["digest"]), observed.isoformat()),
            )
        return {"binding_id": binding_id, "revoked": True, "digest": str(row["digest"])}

    def verify(self, payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        digest = artifact_digest(payload)
        row = self._db.execute(
            "SELECT * FROM artifact_bindings WHERE artifact_id = ?",
            (payload.get("artifact_id"),),
        ).fetchone()
        if row is None:
            raise ValueError("missing artifact binding evidence")
        if int(row["revoked"]) == 1:
            raise ValueError("revoked artifact binding")
        if str(row["digest"]) != digest:
            raise ValueError("tampered or mismatched artifact binding")
        stored = json.loads(str(row["payload_json"]))
        expires = stored.get("expires_at_utc")
        if expires:
            expiry = datetime.fromisoformat(str(expires))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry <= (now or _now()):
                raise ValueError("stale artifact binding")
        return {"binding_id": str(row["binding_id"]), "digest": digest, "verified": True}

    def query(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        if limit < 1 or limit > MAX_QUERY:
            raise ValueError(f"query limit must be between 1 and {MAX_QUERY}")
        if offset < 0:
            raise ValueError("query offset must be non-negative")
        rows = self._db.execute(
            """
            SELECT binding_id, artifact_id, digest, created_at_utc, revoked
            FROM artifact_bindings
            ORDER BY created_at_utc, binding_id
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def audit(self, binding_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """
            SELECT audit_id, binding_id, action, digest, created_at_utc
            FROM artifact_binding_audit
            WHERE binding_id = ?
            ORDER BY audit_id
            """,
            (binding_id,),
        ).fetchall()
        return [dict(row) for row in rows]
