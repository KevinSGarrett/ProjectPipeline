from __future__ import annotations

import tempfile
from pathlib import Path

from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    _materialize_builtin_public_evidence,
)
from project_pipeline.lifecycle.attestation_recovery import (
    EXPECTED_PUBLIC_ATTESTATION_BYTES,
    EXPECTED_PUBLIC_ATTESTATION_SHA256,
    EXPECTED_PUBLIC_QUALIFICATION_BYTES,
    EXPECTED_PUBLIC_QUALIFICATION_SHA256,
    PUBLIC_ATTESTATION_REF,
    PUBLIC_QUALIFICATION_REF,
    sha256_bytes,
)


def test_materialize_builtin_public_evidence_writes_expected_bytes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        wrote = _materialize_builtin_public_evidence(root)
        attestation = (root / PUBLIC_ATTESTATION_REF).read_bytes()
        qualification = (root / PUBLIC_QUALIFICATION_REF).read_bytes()

    assert wrote is True
    assert len(attestation) == EXPECTED_PUBLIC_ATTESTATION_BYTES
    assert len(qualification) == EXPECTED_PUBLIC_QUALIFICATION_BYTES
    assert sha256_bytes(attestation) == EXPECTED_PUBLIC_ATTESTATION_SHA256
    assert sha256_bytes(qualification) == EXPECTED_PUBLIC_QUALIFICATION_SHA256


def test_materialize_builtin_public_evidence_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first = _materialize_builtin_public_evidence(root)
        second = _materialize_builtin_public_evidence(root)

    assert first is True
    assert second is False
