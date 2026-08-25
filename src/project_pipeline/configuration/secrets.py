from __future__ import annotations

import base64
import csv
import ctypes
import json
import os
import socket
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from project_pipeline.configuration.models import SecretReference


class SecretResolutionError(RuntimeError):
    """Raised when an explicitly requested secret reference cannot be resolved safely."""


_DPAPI_BLOB_DIRECTORY = Path(".local") / "secure-secrets" / "dpapi"
_DPAPI_SCHEMA_VERSION = "2.0.0"
_DPAPI_KIND = "windows_current_user_credential_envelope"
_DPAPI_SCOPE_KEYS = frozenset(
    {
        "project_id",
        "cycle_id",
        "machine_id",
        "identity_id",
        "campaign_id",
        "candidate_sha",
        "candidate_tree",
        "scheduler_lease_id",
        "fence_token",
        "expires_at_utc",
    }
)
_ACCESS_LEASE_KIND = "campaign_secret_materialization_access"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_entropy(reference: str, scope: Mapping[str, object]) -> bytes:
    return json.dumps(
        {"reference": reference, "scope": dict(scope)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _windows_dll(name: str) -> Any:
    """Load a Windows DLL after the platform guard without platform-stub leakage."""

    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise SecretResolutionError("Windows DLL loading is unavailable on this platform")
    return loader(name, use_last_error=True)


def current_windows_principal_sid() -> str:
    """Return the immutable SID of the Windows identity that is opening DPAPI."""

    if os.name != "nt":
        raise SecretResolutionError("DPAPI secret resolution is only available on Windows")
    try:
        completed = subprocess.run(
            ["whoami.exe", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        rows = list(csv.reader(completed.stdout.splitlines()))
    except (OSError, subprocess.TimeoutExpired, csv.Error) as error:
        raise SecretResolutionError("Windows principal SID is unavailable") from error
    sid = rows[0][1].strip() if completed.returncode == 0 and rows and len(rows[0]) >= 2 else ""
    if not sid.startswith("S-"):
        raise SecretResolutionError("Windows principal SID is unavailable")
    return sid


def _dpapi_unprotect(ciphertext: bytes, entropy: bytes) -> bytes:
    """Unprotect user-scoped Windows DPAPI bytes without writing plaintext."""

    if os.name != "nt":
        raise SecretResolutionError("DPAPI secret resolution is only available on Windows")
    crypt32 = _windows_dll("crypt32")
    kernel32 = _windows_dll("kernel32")
    cipher_buffer = ctypes.create_string_buffer(ciphertext)
    entropy_buffer = ctypes.create_string_buffer(entropy)
    source = _DataBlob(len(ciphertext), ctypes.cast(cipher_buffer, ctypes.POINTER(ctypes.c_byte)))
    optional_entropy = _DataBlob(
        len(entropy), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_byte))
    )
    output = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        ctypes.byref(optional_entropy),
        None,
        None,
        0,
        ctypes.byref(output),
    )
    if not ok:
        raise SecretResolutionError("DPAPI credential envelope cannot be opened by this Windows identity")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def protect_dpapi_secret(value: str, *, reference: str, scope: Mapping[str, object]) -> bytes:
    """Protect plaintext for a current-user envelope; callers never persist ``value``."""

    if os.name != "nt":
        raise SecretResolutionError("DPAPI secret provisioning is only available on Windows")
    plaintext = value.encode("utf-8")
    entropy = _dpapi_entropy(reference, scope)
    crypt32 = _windows_dll("crypt32")
    kernel32 = _windows_dll("kernel32")
    plain_buffer = ctypes.create_string_buffer(plaintext)
    entropy_buffer = ctypes.create_string_buffer(entropy)
    source = _DataBlob(len(plaintext), ctypes.cast(plain_buffer, ctypes.POINTER(ctypes.c_byte)))
    optional_entropy = _DataBlob(
        len(entropy), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_byte))
    )
    output = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        None,
        ctypes.byref(optional_entropy),
        None,
        None,
        0,
        ctypes.byref(output),
    )
    if not ok:
        raise SecretResolutionError("Windows DPAPI could not protect campaign secret material")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def build_dpapi_secret_envelope(
    value: str, *, reference: SecretReference, scope: Mapping[str, object]
) -> dict[str, object]:
    """Create non-secret binding metadata plus a DPAPI ciphertext envelope."""

    if reference.scheme != "dpapi":
        raise ValueError("DPAPI envelope requires a dpapi:// secret reference")
    if set(scope) != _DPAPI_SCOPE_KEYS or not all(
        str(scope[key]).strip() for key in _DPAPI_SCOPE_KEYS
    ):
        raise ValueError("DPAPI credential envelope scope is incomplete")
    expiry = datetime.fromisoformat(str(scope["expires_at_utc"]).replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(UTC):
        raise ValueError("DPAPI credential envelope expiry must be a future UTC timestamp")
    encrypted = protect_dpapi_secret(value, reference=reference.reference, scope=scope)
    return {
        "schema_version": _DPAPI_SCHEMA_VERSION,
        "kind": _DPAPI_KIND,
        "reference": reference.reference,
        "scope": dict(scope),
        "ciphertext_base64": base64.b64encode(encrypted).decode("ascii"),
        "plaintext_persisted": False,
    }


def _parse_utc_timestamp(value: object, *, label: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise SecretResolutionError(f"{label} is invalid") from error
    if timestamp.tzinfo is None:
        raise SecretResolutionError(f"{label} must be UTC-aware")
    return timestamp.astimezone(UTC)


def _secret_lease_max_seconds(root: Path) -> int:
    """Load the authoritative materialization limit without accepting a fallback."""

    policy_path = root.resolve() / "config" / "security_policy.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        maximum = policy["secret_lease_max_seconds"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SecretResolutionError("secret access policy is unavailable") from error
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
        raise SecretResolutionError("secret access policy limit is invalid")
    return maximum


@dataclass(slots=True)
class CampaignSecretAccessLease:
    """An in-memory, per-materialization authority bounded by security policy."""

    access_id: str
    access_identity: str
    issued_at_utc: datetime
    expires_at_utc: datetime
    scope: dict[str, str]
    revoked: bool = False

    def revoke(self) -> None:
        """Invalidate this process-local access authority before materialization."""

        self.revoked = True

    def redacted_receipt(self, reference: SecretReference) -> dict[str, object]:
        """Return evidence-safe metadata; plaintext is never represented here."""

        return {
            "schema_version": "1.0.0",
            "kind": _ACCESS_LEASE_KIND,
            "access_id": self.access_id,
            "access_identity": self.access_identity,
            "issued_at_utc": self.issued_at_utc.isoformat(),
            "expires_at_utc": self.expires_at_utc.isoformat(),
            "reference": reference.reference,
            "scope": dict(self.scope),
            "revoked": self.revoked,
            "secret_value_observed": False,
            "plaintext_persisted": False,
        }

    def validate(
        self,
        root: Path,
        *,
        required_scope: Mapping[str, str],
        now: datetime | None = None,
    ) -> None:
        if self.revoked:
            raise SecretResolutionError("campaign secret access lease is revoked")
        if not self.access_id.startswith("SACCESS-") or not self.access_identity.strip():
            raise SecretResolutionError("campaign secret access lease identity is invalid")
        normalized_scope = {key: str(value) for key, value in self.scope.items()}
        expected_scope = {key: str(value) for key, value in required_scope.items()}
        if set(normalized_scope) != _DPAPI_SCOPE_KEYS or normalized_scope != expected_scope:
            raise SecretResolutionError("campaign secret access lease scope does not match")
        issued = self.issued_at_utc.astimezone(UTC) if self.issued_at_utc.tzinfo else None
        expires = self.expires_at_utc.astimezone(UTC) if self.expires_at_utc.tzinfo else None
        if issued is None or expires is None or expires <= issued:
            raise SecretResolutionError("campaign secret access lease timestamps are invalid")
        maximum = _secret_lease_max_seconds(root)
        if expires - issued > timedelta(seconds=maximum):
            raise SecretResolutionError("campaign secret access lease exceeds security policy")
        if expires <= (now or datetime.now(UTC)).astimezone(UTC):
            raise SecretResolutionError("campaign secret access lease is expired")


def issue_campaign_secret_access_lease(
    root: Path,
    scope: Mapping[str, str],
    *,
    access_identity: str,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
) -> CampaignSecretAccessLease:
    """Issue one process-local secret-materialization lease up to policy maximum."""

    normalized_scope = {key: str(value) for key, value in scope.items()}
    if set(normalized_scope) != _DPAPI_SCOPE_KEYS or not all(normalized_scope.values()):
        raise SecretResolutionError("campaign credential envelope scope is incomplete")
    if not access_identity.strip():
        raise SecretResolutionError("campaign secret access identity is required")
    issued = (now or datetime.now(UTC)).astimezone(UTC)
    envelope_expiry = _parse_utc_timestamp(
        normalized_scope["expires_at_utc"], label="campaign credential envelope expiry"
    )
    maximum = _secret_lease_max_seconds(root)
    requested_ttl = maximum if ttl_seconds is None else ttl_seconds
    if isinstance(requested_ttl, bool) or not isinstance(requested_ttl, int) or not (
        0 < requested_ttl <= maximum
    ):
        raise SecretResolutionError("campaign secret access lease exceeds security policy")
    expires = min(envelope_expiry, issued + timedelta(seconds=requested_ttl))
    if expires <= issued:
        raise SecretResolutionError("campaign credential envelope is expired")
    return CampaignSecretAccessLease(
        access_id=f"SACCESS-{uuid4().hex.upper()}",
        access_identity=access_identity.strip(),
        issued_at_utc=issued,
        expires_at_utc=expires,
        scope=normalized_scope,
    )


class SecretResolver:
    """Resolve approved secret references only on explicit runtime demand."""

    def __init__(
        self,
        root: Path,
        environment: Mapping[str, str] | None = None,
        *,
        required_scope: Mapping[str, str] | None = None,
        access_lease: CampaignSecretAccessLease | None = None,
    ) -> None:
        self.root = root.resolve()
        self.environment = os.environ if environment is None else environment
        self.required_scope = (
            None
            if required_scope is None
            else {key: str(value) for key, value in required_scope.items()}
        )
        self.access_lease = access_lease
        self.last_access_receipt: dict[str, object] | None = None

    def resolve(self, reference: SecretReference) -> str:
        if reference.scheme == "env":
            value = self.environment.get(reference.target)
            if value is None:
                raise SecretResolutionError(
                    f"required environment secret is unavailable: {reference.reference}"
                )
            return value
        if reference.scheme == "gh-auth":
            return self._resolve_gh_auth(reference)
        if reference.scheme == "dpapi":
            return self._resolve_dpapi(reference)
        candidate = self.root / reference.target
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise SecretResolutionError(
                f"file secret escapes the project root: {reference.reference}"
            ) from error
        try:
            value = resolved.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise SecretResolutionError(
                f"file secret is unavailable: {reference.reference}"
            ) from error
        if not value:
            raise SecretResolutionError(f"file secret is empty: {reference.reference}")
        return value

    def _resolve_gh_auth(self, reference: SecretReference) -> str:
        try:
            completed = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SecretResolutionError("GitHub CLI credential is unavailable") from error
        value = completed.stdout.strip() if completed.returncode == 0 else ""
        if not value:
            raise SecretResolutionError(f"GitHub CLI secret is unavailable: {reference.reference}")
        return value

    def _resolve_dpapi(self, reference: SecretReference) -> str:
        path = self.root / _DPAPI_BLOB_DIRECTORY / f"{reference.target}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SecretResolutionError(
                f"DPAPI credential envelope is unavailable: {reference.reference}"
            ) from error
        if not isinstance(payload, dict) or payload.get("schema_version") != _DPAPI_SCHEMA_VERSION:
            raise SecretResolutionError("DPAPI credential envelope schema is invalid")
        if payload.get("kind") != _DPAPI_KIND or payload.get("reference") != reference.reference:
            raise SecretResolutionError("DPAPI credential envelope reference is invalid")
        scope = payload.get("scope")
        if not isinstance(scope, dict) or set(scope) != _DPAPI_SCOPE_KEYS:
            raise SecretResolutionError("DPAPI credential envelope scope is invalid")
        normalized_scope = {key: str(scope[key]) for key in _DPAPI_SCOPE_KEYS}
        if self.required_scope is None or normalized_scope != self.required_scope:
            raise SecretResolutionError(
                "DPAPI credential envelope scope does not match the bound campaign"
            )
        if self.access_lease is None:
            raise SecretResolutionError("DPAPI credential materialization requires a short-lived access lease")
        self.access_lease.validate(self.root, required_scope=normalized_scope)
        try:
            expiry = _parse_utc_timestamp(
                scope["expires_at_utc"], label="DPAPI credential envelope expiry"
            )
        except KeyError as error:
            raise SecretResolutionError("DPAPI credential envelope expiry is invalid") from error
        if expiry <= datetime.now(UTC):
            raise SecretResolutionError("DPAPI credential envelope is expired")
        machine = normalized_scope["machine_id"]
        identity = normalized_scope["identity_id"]
        actual_machine = socket.gethostname()
        actual_identity = current_windows_principal_sid()
        if (
            machine.casefold() != actual_machine.casefold()
            or identity.casefold() != actual_identity.casefold()
        ):
            raise SecretResolutionError(
                "DPAPI credential envelope scope does not match this Windows identity"
            )
        try:
            ciphertext = base64.b64decode(str(payload["ciphertext_base64"]), validate=True)
            value = _dpapi_unprotect(ciphertext, _dpapi_entropy(reference.reference, scope)).decode(
                "utf-8"
            )
        except (KeyError, ValueError, UnicodeDecodeError, SecretResolutionError) as error:
            if isinstance(error, SecretResolutionError):
                raise
            raise SecretResolutionError("DPAPI credential envelope cannot be decrypted") from error
        if not value:
            raise SecretResolutionError("DPAPI credential envelope resolved to empty material")
        self.last_access_receipt = self.access_lease.redacted_receipt(reference)
        return value
