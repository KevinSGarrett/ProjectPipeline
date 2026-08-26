"""Create a signed, candidate-bound relay for private PP-379 attestation proof."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.autonomy_runtime.live_qualification import (  # noqa: E402
    _COORDINATOR_ATTESTATION_SIGNATURE_NAMESPACE,
    _PRIMARY_COORDINATOR_ID,
    _coordinator_jira_receipt_message,
    create_coordinator_attestation_receipt,
)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=path.parent, prefix=f".{path.name}."
    ) as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def _sign_receipt(*, receipt_sha256: str, signing_key: Path, output: Path) -> None:
    if not signing_key.is_file():
        raise RuntimeError("coordinator signing key is unavailable")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".pp384-sign-") as directory:
        message = Path(directory) / "receipt-sha256.txt"
        message.write_bytes(_coordinator_jira_receipt_message(receipt_sha256))
        completed = subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-Y",
                "sign",
                "-f",
                str(signing_key),
                "-n",
                _COORDINATOR_ATTESTATION_SIGNATURE_NAMESPACE,
                str(message),
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        signature = Path(f"{message}.sig")
        if completed.returncode != 0 or not signature.is_file():
            raise RuntimeError("coordinator attestation receipt signing failed")
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=output.parent, prefix=f".{output.name}."
        ) as stream:
            stream.write(signature.read_bytes())
            temporary = Path(stream.name)
        os.replace(temporary, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--attestation-source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--coordinator-id", default=_PRIMARY_COORDINATOR_ID)
    args = parser.parse_args()
    receipt = create_coordinator_attestation_receipt(
        repository_root=args.root.resolve(),
        attestation_source_root=args.attestation_source_root.resolve(),
        coordinator_id=args.coordinator_id,
    )
    _write_json_atomic(args.output.resolve(), receipt)
    _sign_receipt(
        receipt_sha256=str(receipt["receipt_sha256"]),
        signing_key=args.signing_key.resolve(),
        output=args.signature.resolve(),
    )
    print(
        json.dumps(
            {
                "written": str(args.output.resolve()),
                "status": receipt["status"],
                "candidate": receipt["candidate"],
                "receipt_sha256": receipt["receipt_sha256"],
                "secret_value_observed": False,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
