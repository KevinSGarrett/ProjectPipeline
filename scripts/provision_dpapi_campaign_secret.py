"""Provision one current-user DPAPI campaign-secret lease from standard input.

The plaintext is read once, encrypted before persistence, and never included
in command arguments, stdout, receipts, or the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from project_pipeline.configuration import SecretReference
from project_pipeline.configuration.secrets import build_dpapi_secret_envelope


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--scope-file", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    reference = SecretReference(reference=args.reference)
    if reference.scheme != "dpapi":
        raise SystemExit("--reference must use dpapi://")
    try:
        scope = json.loads(args.scope_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("scope file is unavailable or malformed") from error
    if not isinstance(scope, dict):
        raise SystemExit("scope file must contain one JSON object")
    plaintext = sys.stdin.buffer.read().decode("utf-8").rstrip("\r\n")
    if not plaintext:
        raise SystemExit("secret input is empty")
    envelope = build_dpapi_secret_envelope(plaintext, reference=reference, scope=scope)
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
