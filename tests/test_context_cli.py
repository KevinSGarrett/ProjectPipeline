import json
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextSourceKind,
    ContextTrust,
    DelegationEnvelope,
    Sensitivity,
)


def _write_inputs(tmp_path: Path):
    envelope = DelegationEnvelope.create(
        objective="Review one source file.",
        return_protocol="Return a bounded result.",
        required_context_keys=("src",),
        acceptance_criteria=("Use the requested source.",),
    )
    candidate = ContextCandidate(
        context_key="src",
        kind=ContextSourceKind.SOURCE_FILE,
        content="print('ok')",
        revision_id="sha256:test",
        observed_at_utc=datetime.now(UTC),
        trust=ContextTrust.SOURCE_CONTROLLED,
        sensitivity=Sensitivity.INTERNAL,
        source_reference="src/example.py:L1",
    )
    envelope_path = tmp_path / "envelope.json"
    candidates_path = tmp_path / "candidates.json"
    envelope_path.write_text(json.dumps(envelope.model_dump(mode="json")), encoding="utf-8")
    candidates_path.write_text(json.dumps([candidate.model_dump(mode="json")]), encoding="utf-8")
    return envelope_path, candidates_path


def test_context_cli_compile_status_pack_and_receipt(project_root, tmp_path, capsys):
    envelope, candidates = _write_inputs(tmp_path)
    database = tmp_path / "context.db"
    artifacts = tmp_path / "artifacts"
    assert (
        main(
            [
                "context",
                "compile",
                "--root",
                str(project_root),
                "--database",
                str(database),
                "--envelope",
                str(envelope),
                "--candidates",
                str(candidates),
                "--artifact-root",
                str(artifacts),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    pack_id = result["pack"]["pack_id"]
    assert result["telemetry"]["coverage_score"] == 1.0

    assert (
        main(["context", "status", "--root", str(project_root), "--database", str(database)]) == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["context"]["packs"] == 1

    assert (
        main(
            [
                "context",
                "pack",
                "--root",
                str(project_root),
                "--database",
                str(database),
                "--pack-id",
                pack_id,
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["pack"]["pack_id"] == pack_id

    assert (
        main(
            [
                "context",
                "receipt",
                "--root",
                str(project_root),
                "--database",
                str(database),
                "--pack-id",
                pack_id,
                "--worker-id",
                "worker:test",
                "--receipt-status",
                "CONSUMED",
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["receipt"]["status"] == "CONSUMED"


def test_context_cli_missing_pack_fails_closed(project_root, tmp_path, capsys):
    database = tmp_path / "context.db"
    assert (
        main(
            [
                "context",
                "pack",
                "--root",
                str(project_root),
                "--database",
                str(database),
                "--pack-id",
                "CTXPACK-00000000000000000000",
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "context_pack_not_found"
