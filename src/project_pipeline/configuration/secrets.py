from __future__ import annotations

import base64
import csv
import ctypes
import json
import os
import socket
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.configuration.models import SecretReference


class SecretResolutionError(RuntimeError):
    """Raised when an explicitly requested secret reference cannot be resolved safely."""


_DPAPI_BLOB_DIRECTORY = Path(".local") / "secure-secrets" / "dpapi"
_DPAPI_SCHEMA_VERSION = "1.0.0"
_DPAPI_KIND = "windows_current_user_secret_lease"
_DPAPI_SCOPE_KEYS = frozenset(
    {"project_id", "cycle_id", "machine_id", "identity_id", "lease_id", "expires_at_utc"}
)


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
        raise SecretResolutionError("DPAPI secret lease cannot be opened by this Windows identity")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def protect_dpapi_secret(value: str, *, reference: str, scope: Mapping[str, object]) -> bytes:
    """Protect plaintext for a current-user lease; callers must never persist ``value``."""

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
    """Create non-secret lease metadata plus a DPAPI ciphertext envelope."""

    if reference.scheme != "dpapi":
        raise ValueError("DPAPI envelope requires a dpapi:// secret reference")
    if set(scope) != _DPAPI_SCOPE_KEYS or not all(
        str(scope[key]).strip() for key in _DPAPI_SCOPE_KEYS
    ):
        raise ValueError("DPAPI secret lease scope is incomplete")
    expiry = datetime.fromisoformat(str(scope["expires_at_utc"]).replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(UTC):
        raise ValueError("DPAPI secret lease expiry must be a future UTC timestamp")
    encrypted = protect_dpapi_secret(value, reference=reference.reference, scope=scope)
    return {
        "schema_version": _DPAPI_SCHEMA_VERSION,
        "kind": _DPAPI_KIND,
        "reference": reference.reference,
        "scope": dict(scope),
        "ciphertext_base64": base64.b64encode(encrypted).decode("ascii"),
        "plaintext_persisted": False,
    }


class SecretResolver:
    """Resolve approved secret references only on explicit runtime demand."""

    def __init__(
        self,
        root: Path,
        environment: Mapping[str, str] | None = None,
        *,
        required_scope: Mapping[str, str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.environment = os.environ if environment is None else environment
        self.required_scope = (
            None
            if required_scope is None
            else {key: str(value) for key, value in required_scope.items()}
        )

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
                f"DPAPI secret lease is unavailable: {reference.reference}"
            ) from error
        if not isinstance(payload, dict) or payload.get("schema_version") != _DPAPI_SCHEMA_VERSION:
            raise SecretResolutionError("DPAPI secret lease schema is invalid")
        if payload.get("kind") != _DPAPI_KIND or payload.get("reference") != reference.reference:
            raise SecretResolutionError("DPAPI secret lease reference is invalid")
        scope = payload.get("scope")
        if not isinstance(scope, dict) or set(scope) != _DPAPI_SCOPE_KEYS:
            raise SecretResolutionError("DPAPI secret lease scope is invalid")
        normalized_scope = {key: str(scope[key]) for key in _DPAPI_SCOPE_KEYS}
        if self.required_scope is None or normalized_scope != self.required_scope:
            raise SecretResolutionError(
                "DPAPI secret lease scope does not match the bound campaign"
            )
        try:
            expiry = datetime.fromisoformat(str(scope["expires_at_utc"]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as error:
            raise SecretResolutionError("DPAPI secret lease expiry is invalid") from error
        if expiry.tzinfo is None or expiry <= datetime.now(UTC):
            raise SecretResolutionError("DPAPI secret lease is expired")
        machine = normalized_scope["machine_id"]
        identity = normalized_scope["identity_id"]
        actual_machine = socket.gethostname()
        actual_identity = current_windows_principal_sid()
        if (
            machine.casefold() != actual_machine.casefold()
            or identity.casefold() != actual_identity.casefold()
        ):
            raise SecretResolutionError(
                "DPAPI secret lease scope does not match this Windows identity"
            )
        try:
            ciphertext = base64.b64decode(str(payload["ciphertext_base64"]), validate=True)
            value = _dpapi_unprotect(ciphertext, _dpapi_entropy(reference.reference, scope)).decode(
                "utf-8"
            )
        except (KeyError, ValueError, UnicodeDecodeError, SecretResolutionError) as error:
            if isinstance(error, SecretResolutionError):
                raise
            raise SecretResolutionError("DPAPI secret lease cannot be decrypted") from error
        if not value:
            raise SecretResolutionError("DPAPI secret lease resolved to empty material")
        return value
