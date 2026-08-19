from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_pipeline.assurance.requirement_reconciliation import (
    apply_evidence_bound_requirement_states,
    evaluate_requirement_reconciliation,
    propose_evidence_bound_requirement_states,
)
from project_pipeline.cli import main
from project_pipeline.io import read_jsonl, sha256_canonical_file, write_json, write_jsonl

ROOT = Path(__file__).resolve().parents[1]
CURRENT_SHA = "c" * 40
CURRENT_TREE = "d" * 40


def _candidate_row() -> dict:
    source = read_jsonl(ROOT / "plans/_traceability/requirements.jsonl")
    return next(
        row
        for row in source
        if row.get("implementation_state") == "PARTIALLY_IMPLEMENTED"
        and row.get("implementation_paths")
        and row.get("test_ids")
        and row.get("evidence_ids")
        and row["requirement_id"] not in {"REQ-PDEF-0011", "REQ-CTRL-0004"}
        and "live" not in str(row.get("acceptance_summary", "")).lower()
        and "24-hour" not in str(row.get("acceptance_summary", "")).lower()
    )


def _seed_valid(tmp_path: Path, row: dict, *, evidence_updates: dict | None = None) -> dict:
    target = tmp_path / "plans/_traceability/requirements.jsonl"
    target.parent.mkdir(parents=True)
    write_jsonl(target, [row])
    for relative in row["implementation_paths"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative.endswith("/"):
            (path / "module.py").write_text("value = 1\n", encoding="utf-8")
        else:
            path.write_text("present\n", encoding="utf-8")
    tests = []
    for test_id in row["test_ids"]:
        test_path = f"tests/test_{test_id.lower().replace('-', '_')}.py"
        callable_name = f"test_{test_id.lower().replace('-', '_')}"
        file = tmp_path / test_path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"def {callable_name}():\n    assert 1 == 1\n", encoding="utf-8")
        tests.append({"test_id": test_id, "path": test_path, "callable": callable_name})
    write_json(
        tmp_path / "tests" / "TEST_CATALOG.json",
        {"schema_version": "2.0.0", "test_count": len(tests), "tests": tests},
    )
    artifact = tmp_path / "evidence" / "receipt.txt"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("passing receipt\n", encoding="utf-8")
    record = {
        "artifact_path": "evidence/receipt.txt",
        "claim": f"pytest {row['test_ids'][0]} passed",
        "criterion_ids": ["AC-TEST-01"],
        "environment": "local_build_environment",
        "evidence_id": row["evidence_ids"][0],
        "method": "pytest",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "requirement_ids": [row["requirement_id"]],
        "result": "PASS",
        "schema_version": "1.0.0",
        "sha256": sha256_canonical_file(artifact),
        "supersedes": None,
        "test_ids": list(row["test_ids"]),
        "verification_status": "VERIFIED",
        "integrated_sha": CURRENT_SHA,
        "integrated_tree": CURRENT_TREE,
    }
    if evidence_updates:
        record.update(evidence_updates)
        if "artifact_path" in evidence_updates:
            extra = tmp_path / str(evidence_updates["artifact_path"])
            extra.parent.mkdir(parents=True, exist_ok=True)
            if not extra.exists():
                extra.write_text("other\n", encoding="utf-8")
            record["sha256"] = sha256_canonical_file(extra)
    records = []
    for evidence_id in row["evidence_ids"]:
        item = dict(record)
        item["evidence_id"] = evidence_id
        records.append(json.dumps(item))
    (tmp_path / "evidence" / "EVIDENCE_LEDGER.jsonl").write_text(
        "\n".join(records) + "\n", encoding="utf-8"
    )
    return record


def test_evidence_bound_reconciliation_requires_artifacts_tests_and_evidence(
    tmp_path: Path,
) -> None:
    candidate = _candidate_row()
    _seed_valid(tmp_path, candidate)
    proposals = propose_evidence_bound_requirement_states(
        tmp_path, current_sha=CURRENT_SHA, current_tree=CURRENT_TREE
    )
    assert proposals
    assert proposals[0]["requirement_id"] == candidate["requirement_id"]
    applied = apply_evidence_bound_requirement_states(
        tmp_path, limit=1, current_sha=CURRENT_SHA, current_tree=CURRENT_TREE
    )
    assert applied[0]["next_state"] == "IMPLEMENTED"
    assert (
        read_jsonl(tmp_path / "plans/_traceability/requirements.jsonl")[0]["implementation_state"]
        == "IMPLEMENTED"
    )


def test_reconciliation_rejects_false_positive_classes(tmp_path: Path) -> None:
    candidate = _candidate_row()

    def reason_for(**updates) -> str:
        workspace = tmp_path / updates.get("_space", "case")
        workspace.mkdir(parents=True, exist_ok=True)
        row = dict(candidate)
        if "_row" in updates:
            row.update(updates["_row"])
        _seed_valid(workspace, row, evidence_updates=updates.get("_evidence"))
        if updates.get("_delete_catalog"):
            (workspace / "tests" / "TEST_CATALOG.json").write_text(
                json.dumps({"schema_version": "2.0.0", "test_count": 0, "tests": []}),
                encoding="utf-8",
            )
        if updates.get("_fabricated"):
            row["evidence_ids"] = ["EVID-FABRICATED"]
            write_jsonl(workspace / "plans/_traceability/requirements.jsonl", [row])
        if updates.get("_empty_dir"):
            empty = workspace / "empty_impl"
            empty.mkdir(parents=True, exist_ok=True)
            row["implementation_paths"] = ["empty_impl"]
            write_jsonl(workspace / "plans/_traceability/requirements.jsonl", [row])
        ledger = evaluate_requirement_reconciliation(
            workspace, current_sha=CURRENT_SHA, current_tree=CURRENT_TREE
        )
        return ledger[0]["reason"]

    assert "not in TEST_CATALOG" in reason_for(_space="catalog", _delete_catalog=True)
    assert "missing from the ledger" in reason_for(_space="missing-ev", _fabricated=True)
    assert "records FAIL" in reason_for(_space="fail", _evidence={"result": "FAIL"})
    assert "is stale" in reason_for(
        _space="stale",
        _evidence={"observed_at_utc": (datetime.now(UTC) - timedelta(days=40)).isoformat()},
    )
    assert "different integrated SHA" in reason_for(
        _space="sha",
        _evidence={"integrated_sha": "a" * 40},
    )
    live_reason = reason_for(
        _space="mock",
        _row={
            "acceptance_summary": "Verified when live unattended Windows behavior holds",
            "title": "live unattended",
            "statement": "live unattended",
        },
        _evidence={"environment": "mock"},
    )
    assert "live" in live_reason or "mock-only" in live_reason
    assert "empty, or unfingerprintable" in reason_for(_space="emptydir", _empty_dir=True)
    protected = dict(candidate)
    protected["requirement_id"] = "REQ-PDEF-0011"
    workspace = tmp_path / "protected"
    _seed_valid(workspace, protected)
    assert (
        "protected"
        in evaluate_requirement_reconciliation(
            workspace, current_sha=CURRENT_SHA, current_tree=CURRENT_TREE
        )[0]["reason"]
    )
    unbound = reason_for(_space="unbound", _evidence={"integrated_sha": "", "integrated_tree": ""})
    assert "unbound from the current head" in unbound
    missing_identity = evaluate_requirement_reconciliation(tmp_path / "sha")[0]["reason"]
    assert "current repository SHA/tree is required" in missing_identity


def test_full_repository_ledger_covers_every_requirement() -> None:
    ledger = evaluate_requirement_reconciliation(ROOT)
    rows = read_jsonl(ROOT / "plans/_traceability/requirements.jsonl")
    assert len(ledger) == len(rows) == 352
    assert {item["requirement_id"] for item in ledger} == {
        str(item["requirement_id"]) for item in rows
    }
    assert all("reason" in item and "accepted" in item for item in ledger)


def test_requirement_reconcile_cli_requires_approve_and_dry_runs(tmp_path, capsys) -> None:
    candidate = _candidate_row()
    _seed_valid(tmp_path, candidate)
    code = main(["requirement-reconcile", "--root", str(tmp_path), "--apply"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "configuration_invalid"
    assert main(["requirement-reconcile", "--root", str(tmp_path), "--limit", "1"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["mode"] == "DRY_RUN"
    assert dry["ledger_count"] == 1
