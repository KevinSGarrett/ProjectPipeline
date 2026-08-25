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
from pathlib import Path

from project_pipeline.configuration import SecretReference
from project_pipeline.configuration.campaign_environment import campaign_secret_scope
from project_pipeline.configuration.secrets import (
    build_dpapi_secret_envelope,
    current_windows_principal_sid,
)


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
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
        if os.name == "nt":
            identity = os.environ.get("USERNAME", "")
            acl = subprocess.run(
                ["icacls.exe", str(temporary), "/inheritance:r", "/grant:r", f"{identity}:(R,W)"],
                capture_output=True,
                text=True,
                check=False,
            )
            if acl.returncode:
                raise RuntimeError("DPAPI secret lease ACL could not be restricted")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _revoke(root: Path, reference: SecretReference, receipt_path: Path) -> dict[str, object]:
    """Remove one exact encrypted envelope and leave a non-secret readback receipt."""

    destination = root / ".local" / "secure-secrets" / "dpapi" / f"{reference.target}.json"
    try:
        payload = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("DPAPI secret lease is unavailable for revocation") from error
    if not isinstance(payload, dict) or payload.get("reference") != reference.reference:
        raise RuntimeError("DPAPI secret lease reference does not match revocation request")
    scope = payload.get("scope")
    if not isinstance(scope, dict):
        raise RuntimeError("DPAPI secret lease scope is invalid for revocation")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.unlink()
    if destination.exists():
        raise RuntimeError("DPAPI secret lease revocation readback failed")
    receipt = {
        "schema_version": "1.0.0",
        "kind": "dpapi_campaign_secret_revocation",
        "reference": reference.reference,
        "destination": str(destination),
        "ciphertext_sha256_before_revocation": digest,
        "scope": scope,
        "revoked": True,
        "readback_absent": True,
        "secret_value_observed": False,
        "user_action_required": False,
    }
    _write_atomic(receipt_path, receipt)
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
        if args.scope_file is not None or args.revocation_receipt is None:
            raise SystemExit(
                "revocation requires --revocation-receipt and does not accept --scope-file"
            )
        receipt = _revoke(root, reference, args.revocation_receipt.resolve())
        print(json.dumps(receipt, sort_keys=True))
        return 0
    if args.scope_file is None:
        raise SystemExit("provisioning requires --scope-file")
    try:
        scope = json.loads(args.scope_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("scope file is unavailable or malformed") from error
    if not isinstance(scope, dict):
        raise SystemExit("scope file must contain one JSON object")
    try:
        normalized_scope = campaign_secret_scope({key: str(value) for key, value in scope.items()})
    except Exception as error:
        raise SystemExit("scope file is not an eligible Cycle 16-B credential scope") from error
    if normalized_scope["machine_id"].casefold() != socket.gethostname().casefold():
        raise SystemExit("scope file is not bound to this CPU machine")
    if normalized_scope["identity_id"] != current_windows_principal_sid():
        raise SystemExit("scope file is not bound to this scheduled Windows principal")
    plaintext = sys.stdin.buffer.read().decode("utf-8").rstrip("\r\n")
    if not plaintext:
        raise SystemExit("secret input is empty")
    envelope = build_dpapi_secret_envelope(plaintext, reference=reference, scope=normalized_scope)
    destination = root / ".local" / "secure-secrets" / "dpapi" / f"{reference.target}.json"
    _write_atomic(destination, envelope)
    print(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "kind": "dpapi_campaign_secret_provisioning",
                "reference": reference.reference,
                "destination": str(destination),
                "ciphertext_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "scope": scope,
                "secret_value_observed": False,
                "plaintext_persisted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
