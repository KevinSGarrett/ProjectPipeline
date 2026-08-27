from __future__ import annotations

import tempfile
from pathlib import Path

from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    _materialize_builtin_public_evidence,
    qualify_cursor_cli_provider,
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


def test_builtin_evidence_bootstrap_never_mutates_candidate_checkout(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    disposable = tmp_path / "disposable"

    report = qualify_cursor_cli_provider(
        repository_root=candidate,
        disposable_root=disposable,
    )

    discovery = report["phases"][0]["observations"]
    assert discovery["bootstrap_materialized_builtin_public_evidence"] is True
    assert not (candidate / PUBLIC_ATTESTATION_REF).exists()
    assert not (candidate / PUBLIC_QUALIFICATION_REF).exists()
    assert not (candidate / ".local").exists()
    assert (disposable / "cursor-cli-durable" / "privacy_attestation.json").is_file()
    assert (disposable / "cursor-cli-durable" / "provider_qualification.json").is_file()


def test_signed_coordinator_relay_never_materializes_private_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    private_source = tmp_path / "private-source"
    for evidence_ref in (PUBLIC_ATTESTATION_REF, PUBLIC_QUALIFICATION_REF):
        evidence_path = private_source / evidence_ref
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(b"private coordinator evidence")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a signed relay must not process raw private evidence")

    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.cursor_cli_qualification.evaluate_attestation_recovery",
        forbidden,
    )
    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.cursor_cli_qualification._materialize_builtin_public_evidence",
        forbidden,
    )

    report = qualify_cursor_cli_provider(
        repository_root=candidate,
        disposable_root=tmp_path / "disposable",
        source_root=private_source,
        coordinator_attestation={
            "valid": True,
            "signature_verified": True,
            "relay": "signed-private-attestation",
        },
    )

    discovery = report["phases"][0]["observations"]
    assert discovery["relay_prevented_raw_evidence_materialization"] is True
    assert not (candidate / PUBLIC_ATTESTATION_REF).exists()
    assert not (candidate / PUBLIC_QUALIFICATION_REF).exists()
    assert not (tmp_path / "disposable" / "evidence-verify").exists()
