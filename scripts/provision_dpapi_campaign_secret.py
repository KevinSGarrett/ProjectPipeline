"""Provision one current-user DPAPI campaign-secret lease from standard input.

The plaintext is read once, encrypted before persistence, and never included
in command arguments, stdout, receipts, or the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from project_pipeline.configuration import SecretReference
from project_pipeline.configuration.campaign_environment import campaign_secret_scope
from project_pipeline.configuration.secrets import (
    build_dpapi_secret_envelope,
    current_windows_principal_sid,
)


def _write_atomic(path: Path, payload: dict[str, object], *, replace: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise RuntimeError(
            "DPAPI secret lease already exists; replacement requires explicit revocation"
        )
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=path.parent, prefix=f".{path.name}."
    ) as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_dpapi_envelope(path: Path, payload: dict[str, object]) -> None:
    """Persist one encrypted envelope atomically, then restrict it to its owner."""

    _write_atomic(path, payload)
    if os.name != "nt":
        return
    identity = os.environ.get("USERNAME", "")
    acl = subprocess.run(
        ["icacls.exe", str(path), "/inheritance:r", "/grant:r", f"{identity}:(M)"],
        capture_output=True,
        text=True,
        check=False,
    )
    if acl.returncode:
        with suppress(OSError):
            path.unlink()
        raise RuntimeError("DPAPI secret lease ACL could not be restricted")


def _load_scope(scope_file: Path, *, allow_expired: bool) -> dict[str, str]:
    try:
        scope = json.loads(scope_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("scope file is unavailable or malformed") from error
    if not isinstance(scope, dict):
        raise RuntimeError("scope file must contain one JSON object")
    try:
        return campaign_secret_scope(
            {key: str(value) for key, value in scope.items()},
            require_fresh_campaign_window=not allow_expired,
            allow_expired=allow_expired,
        )
    except Exception as error:
        raise RuntimeError("scope file is not an eligible Cycle 16-B credential scope") from error


def _require_local_scope(scope: dict[str, str]) -> None:
    if scope["machine_id"].casefold() != socket.gethostname().casefold():
        raise RuntimeError("scope file is not bound to this CPU machine")
    if scope["identity_id"] != current_windows_principal_sid():
        raise RuntimeError("scope file is not bound to this scheduled Windows principal")


def _receipt_path(root: Path, receipt_path: Path, destination: Path) -> Path:
    resolved = receipt_path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise RuntimeError(
            "revocation receipt must remain within the campaign workspace"
        ) from error
    if resolved == destination.resolve():
        raise RuntimeError("revocation receipt must not replace the encrypted envelope")
    return resolved


def _receipt(
    *,
    state: str,
    reference: SecretReference,
    destination: Path,
    ciphertext_sha256: str,
    scope: dict[str, str],
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "kind": "dpapi_campaign_secret_revocation",
        "state": state,
        "reference": reference.reference,
        "destination": str(destination),
        "ciphertext_sha256_before_revocation": ciphertext_sha256,
        "scope": scope,
        "secret_value_observed": False,
        "user_action_required": False,
    }


def _reconcile_existing_intent(
    *,
    receipt_path: Path,
    destination: Path,
    reference: SecretReference,
    expected_scope: dict[str, str],
) -> dict[str, object] | None:
    if not receipt_path.exists():
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("revocation receipt is unavailable or malformed") from error
    if not isinstance(receipt, dict):
        raise RuntimeError("revocation receipt is invalid")
    if (
        receipt.get("kind") != "dpapi_campaign_secret_revocation"
        or receipt.get("reference") != reference.reference
        or receipt.get("scope") != expected_scope
    ):
        raise RuntimeError("revocation receipt does not match the requested credential scope")
    state = receipt.get("state")
    if state in {"REVOKED", "REVOKED_RECONCILED"}:
        if destination.exists():
            raise RuntimeError("revocation receipt conflicts with a present encrypted envelope")
        return receipt
    if state != "REVOCATION_INTENT":
        raise RuntimeError("revocation receipt records an unresolved outcome")
    if destination.exists():
        raise RuntimeError("revocation intent outcome is unknown; refusing another deletion")
    reconciled = dict(receipt)
    reconciled.update({"state": "REVOKED_RECONCILED", "revoked": True, "readback_absent": True})
    _write_atomic(receipt_path, reconciled, replace=True)
    return reconciled


def _revoke(
    root: Path,
    reference: SecretReference,
    expected_scope: dict[str, str],
    receipt_path: Path,
) -> dict[str, object]:
    """Remove one fully bound envelope only after a durable revocation intent exists."""

    destination = root / ".local" / "secure-secrets" / "dpapi" / f"{reference.target}.json"
    receipt_path = _receipt_path(root, receipt_path, destination)
    reconciled = _reconcile_existing_intent(
        receipt_path=receipt_path,
        destination=destination,
        reference=reference,
        expected_scope=expected_scope,
    )
    if reconciled is not None:
        return reconciled
    try:
        payload = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("DPAPI secret lease is unavailable for revocation") from error
    if not isinstance(payload, dict) or payload.get("reference") != reference.reference:
        raise RuntimeError("DPAPI secret lease reference does not match revocation request")
    scope = payload.get("scope")
    if (
        not isinstance(scope, dict)
        or {key: str(value) for key, value in scope.items()} != expected_scope
    ):
        raise RuntimeError("DPAPI secret lease scope does not match revocation request")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    intent = _receipt(
        state="REVOCATION_INTENT",
        reference=reference,
        destination=destination,
        ciphertext_sha256=digest,
        scope=expected_scope,
    )
    intent.update({"revoked": False, "readback_absent": False})
    _write_atomic(receipt_path, intent)
    try:
        destination.unlink()
    except OSError as error:
        failed = dict(intent)
        failed["state"] = "DELETE_FAILED"
        _write_atomic(receipt_path, failed, replace=True)
        raise RuntimeError("DPAPI secret lease deletion failed after durable intent") from error
    if destination.exists():
        failed = dict(intent)
        failed["state"] = "DELETE_READBACK_FAILED"
        _write_atomic(receipt_path, failed, replace=True)
        raise RuntimeError("DPAPI secret lease revocation readback failed")
    receipt = _receipt(
        state="REVOKED",
        reference=reference,
        destination=destination,
        ciphertext_sha256=digest,
        scope=expected_scope,
    )
    receipt.update({"revoked": True, "readback_absent": True})
    _write_atomic(receipt_path, receipt, replace=True)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--scope-file", type=Path)
    parser.add_argument("--revoke", action="store_true")
    parser.add_argument("--revocation-receipt", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    reference = SecretReference(reference=args.reference)
    if reference.scheme != "dpapi":
        raise SystemExit("--reference must use dpapi://")
    if args.revoke:
        if args.scope_file is None or args.revocation_receipt is None:
            raise SystemExit("revocation requires --scope-file and --revocation-receipt")
        try:
            scope = _load_scope(args.scope_file.resolve(), allow_expired=True)
            _require_local_scope(scope)
            receipt = _revoke(root, reference, scope, args.revocation_receipt.resolve())
        except RuntimeError as error:
            raise SystemExit(str(error)) from error
        print(json.dumps(receipt, sort_keys=True))
        return 0
    if args.scope_file is None:
        raise SystemExit("provisioning requires --scope-file")
    try:
        normalized_scope = _load_scope(args.scope_file.resolve(), allow_expired=False)
        _require_local_scope(normalized_scope)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    plaintext = sys.stdin.buffer.read().decode("utf-8").rstrip("\r\n")
    if not plaintext:
        raise SystemExit("secret input is empty")
    envelope = build_dpapi_secret_envelope(plaintext, reference=reference, scope=normalized_scope)
    destination = root / ".local" / "secure-secrets" / "dpapi" / f"{reference.target}.json"
    _write_dpapi_envelope(destination, envelope)
    print(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "kind": "dpapi_campaign_secret_provisioning",
                "reference": reference.reference,
                "destination": str(destination),
                "ciphertext_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "scope": normalized_scope,
                "secret_value_observed": False,
                "plaintext_persisted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
