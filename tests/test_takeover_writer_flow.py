from __future__ import annotations

import hashlib
import json
from pathlib import Path

import project_pipeline.lifecycle.takeover_cli as takeover_cli
from project_pipeline.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _write_evidence(path: Path, payload: dict[str, object]) -> str:
    body = (json.dumps(payload) + "\n").encode("utf-8")
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def test_takeover_writer_binds_evidence_reference_and_fingerprint(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    attestation_state = tmp_path / "privacy_attestation.json"
    monkeypatch.setenv("PROJECT_PIPELINE_TAKEOVER_ATTESTATION_PATH", str(attestation_state))
    evidence_path = tmp_path / "attestation-evidence.json"
    expected_evidence_fingerprint = _write_evidence(
        evidence_path,
        {
            "project_id": "PROJECT-PIPELINE",
            "provider_id": "provider:cursor-cli",
            "scope": "local-governed-phase1",
            "approved": True,
            "approved_at_utc": "2026-08-16T21:00:00+00:00",
        },
    )

    assert (
        main(
            [
                "takeover",
                "write-attestation",
                "--root",
                str(ROOT),
                "--project-id",
                "PROJECT-PIPELINE",
                "--provider-id",
                "provider:cursor-cli",
                "--scope",
                "local-governed-phase1",
                "--evidence-ref",
                str(evidence_path),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    record = result["record"]
    assert record["evidence_fingerprint"] == expected_evidence_fingerprint
    assert record["evidence_ref"] == str(evidence_path.resolve())
    persisted = json.loads(attestation_state.read_text(encoding="utf-8"))
    assert persisted["evidence_ref"] == record["evidence_ref"]
    assert persisted["evidence_fingerprint"] == expected_evidence_fingerprint


def test_takeover_writer_fails_for_missing_or_unreadable_evidence(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    missing_path = tmp_path / "missing-evidence.json"
    assert (
        main(
            [
                "takeover",
                "write-attestation",
                "--root",
                str(ROOT),
                "--project-id",
                "PROJECT-PIPELINE",
                "--provider-id",
                "provider:cursor-cli",
                "--scope",
                "local-governed-phase1",
                "--evidence-ref",
                str(missing_path),
            ]
        )
        == 1
    )
    missing_result = json.loads(capsys.readouterr().out)
    assert missing_result["ok"] is False
    assert "missing_evidence_artifact" in missing_result["reasons"]

    evidence_path = tmp_path / "provider-evidence.json"
    _write_evidence(
        evidence_path,
        {
            "project_id": "PROJECT-PIPELINE",
            "provider_id": "provider:cursor-cli",
            "scope": "local-governed-phase1",
            "qualified": True,
            "verified_at_utc": "2026-08-16T21:00:00+00:00",
        },
    )
    original_read_bytes = takeover_cli.Path.read_bytes

    def _raising_read_bytes(self: Path) -> bytes:
        if self.resolve() == evidence_path.resolve():
            raise OSError("permission denied")
        return original_read_bytes(self)

    monkeypatch.setattr(takeover_cli.Path, "read_bytes", _raising_read_bytes)
    assert (
        main(
            [
                "takeover",
                "write-provider-qualification",
                "--root",
                str(ROOT),
                "--project-id",
                "PROJECT-PIPELINE",
                "--provider-id",
                "provider:cursor-cli",
                "--scope",
                "local-governed-phase1",
                "--evidence-ref",
                str(evidence_path),
            ]
        )
        == 1
    )
    unreadable_result = json.loads(capsys.readouterr().out)
    assert unreadable_result["ok"] is False
    assert unreadable_result["reasons"] == ["unreadable_evidence_artifact"]


def test_takeover_writer_rejects_identity_mismatch(tmp_path: Path, capsys) -> None:
    evidence_path = tmp_path / "bad-identity-evidence.json"
    _write_evidence(
        evidence_path,
        {
            "project_id": "OTHER-PROJECT",
            "provider_id": "provider:cursor-cli",
            "scope": "local-governed-phase1",
            "approved": True,
            "approved_at_utc": "2026-08-16T21:00:00+00:00",
        },
    )
    assert (
        main(
            [
                "takeover",
                "write-attestation",
                "--root",
                str(ROOT),
                "--project-id",
                "PROJECT-PIPELINE",
                "--provider-id",
                "provider:cursor-cli",
                "--scope",
                "local-governed-phase1",
                "--evidence-ref",
                str(evidence_path),
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert "evidence_identity_mismatch" in result["reasons"]
