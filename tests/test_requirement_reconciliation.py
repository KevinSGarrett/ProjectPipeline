from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.assurance.requirement_reconciliation import (
    apply_evidence_bound_requirement_states,
    propose_evidence_bound_requirement_states,
)
from project_pipeline.cli import main
from project_pipeline.io import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parents[1]


def test_evidence_bound_reconciliation_requires_artifacts_tests_and_evidence(
    tmp_path: Path,
) -> None:
    source = ROOT / "plans/_traceability/requirements.jsonl"
    target = tmp_path / "plans/_traceability/requirements.jsonl"
    target.parent.mkdir(parents=True)
    rows = read_jsonl(source)
    candidate = next(
        row
        for row in rows
        if row.get("implementation_state") == "PARTIALLY_IMPLEMENTED"
        and row.get("implementation_paths")
        and row.get("test_ids")
        and row.get("evidence_ids")
        and row["requirement_id"] not in {"REQ-PDEF-0011", "REQ-CTRL-0004"}
    )
    for relative in candidate["implementation_paths"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("present\n", encoding="utf-8")
    write_jsonl(target, [candidate])

    proposals = propose_evidence_bound_requirement_states(tmp_path)
    assert proposals
    assert proposals[0]["requirement_id"] == candidate["requirement_id"]
    applied = apply_evidence_bound_requirement_states(tmp_path, limit=1)
    assert applied[0]["next_state"] == "IMPLEMENTED"
    assert read_jsonl(target)[0]["implementation_state"] == "IMPLEMENTED"


def test_requirement_reconcile_cli_requires_approve_and_dry_runs(tmp_path, capsys) -> None:
    source = ROOT / "plans/_traceability/requirements.jsonl"
    target = tmp_path / "plans/_traceability/requirements.jsonl"
    target.parent.mkdir(parents=True)
    rows = read_jsonl(source)[:3]
    write_jsonl(target, rows)
    code = main(["requirement-reconcile", "--root", str(tmp_path), "--apply"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "configuration_invalid"
    assert main(["requirement-reconcile", "--root", str(tmp_path), "--limit", "1"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["mode"] == "DRY_RUN"
