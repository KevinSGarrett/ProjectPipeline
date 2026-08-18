from __future__ import annotations

import hashlib
import json
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.lifecycle import DurableProviderQualificationEvidence

ROOT = Path(__file__).resolve().parents[1]


def _write_json_with_fingerprint(path: Path, payload: dict[str, object]) -> str:
    body = (json.dumps(payload) + "\n").encode("utf-8")
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def test_control_and_scheduler_share_reconciled_gate_outputs(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    identity = {
        "project_id": "PROJECT-PIPELINE",
        "provider_id": "provider:cursor-cli",
        "scope": "local-governed-phase1",
    }
    attestation = tmp_path / "attestation.json"
    qualification = tmp_path / "provider-qualification.json"
    signals = tmp_path / "signals.json"
    signals.write_text(json.dumps({"schema_version": "1.0.0", "queue_depth": 0}), encoding="utf-8")
    monkeypatch.setenv("PROJECT_PIPELINE_TAKEOVER_ATTESTATION_PATH", str(attestation))
    monkeypatch.setenv("PROJECT_PIPELINE_PROVIDER_QUALIFICATION_PATH", str(qualification))

    control_db = tmp_path / "control.db"
    assert main(["control", "sequence", "--root", str(ROOT), "--database", str(control_db)]) == 0
    control_initial = json.loads(capsys.readouterr().out)
    expected_attestation_fingerprint = control_initial["takeover_governor"]["attestation"][
        "expected_fingerprint"
    ]

    attestation_evidence = tmp_path / "attestation-evidence.json"
    attestation_evidence_fingerprint = _write_json_with_fingerprint(
        attestation_evidence,
        {
            **identity,
            "approved": True,
            "approved_at_utc": "2026-08-16T21:00:00+00:00",
        },
    )
    provider_evidence = tmp_path / "provider-evidence.json"
    provider_evidence_fingerprint = _write_json_with_fingerprint(
        provider_evidence,
        {
            **identity,
            "qualified": True,
            "verified_at_utc": "2026-08-16T21:00:00+00:00",
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
                identity["project_id"],
                "--provider-id",
                identity["provider_id"],
                "--scope",
                identity["scope"],
                "--evidence-ref",
                str(attestation_evidence),
            ]
        )
        == 0
    )
    attestation_write = json.loads(capsys.readouterr().out)
    assert attestation_write["record"]["fingerprint"] == expected_attestation_fingerprint
    assert attestation_write["record"]["evidence_fingerprint"] == attestation_evidence_fingerprint
    assert (
        main(
            [
                "takeover",
                "write-provider-qualification",
                "--root",
                str(ROOT),
                "--project-id",
                identity["project_id"],
                "--provider-id",
                identity["provider_id"],
                "--scope",
                identity["scope"],
                "--evidence-ref",
                str(provider_evidence),
            ]
        )
        == 0
    )
    provider_write = json.loads(capsys.readouterr().out)
    assert provider_write["record"][
        "fingerprint"
    ] == DurableProviderQualificationEvidence.fingerprint_for(
        project_id="PROJECT-PIPELINE",
        provider_id="provider:cursor-cli",
        scope="local-governed-phase1",
        qualified=True,
    )
    assert provider_write["record"]["evidence_fingerprint"] == provider_evidence_fingerprint

    assert main(["control", "sequence", "--root", str(ROOT), "--database", str(control_db)]) == 0
    control_result = json.loads(capsys.readouterr().out)

    scheduler_db = tmp_path / "scheduler.db"
    assert (
        main(
            [
                "scheduler",
                "plan",
                "--root",
                str(ROOT),
                "--database",
                str(scheduler_db),
                "--max-lanes",
                "2",
                "--signals-file",
                str(signals),
            ]
        )
        == 0
    )
    scheduler_result = json.loads(capsys.readouterr().out)

    assert (
        control_result["takeover_governor"]["gate_reconciliation"]
        == scheduler_result["takeover_governor"]["gate_reconciliation"]
    )
