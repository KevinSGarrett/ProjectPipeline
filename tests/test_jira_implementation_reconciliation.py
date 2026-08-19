from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from project_pipeline.assurance.jira_implementation_reconciliation import (
    apply_jira_implementation_reconciliation,
    evaluate_jira_implementation_reconciliation,
)
from project_pipeline.cli import main
from project_pipeline.io import read_json, sha256_canonical_file, write_json, write_jsonl
from project_pipeline.jira import rebuild_jira_indexes

ROOT = Path(__file__).resolve().parents[1]


def _seed(tmp_path: Path) -> dict[str, Path]:
    requirement = {
        "requirement_id": "REQ-TEST-0001",
        "disposition": "ACCEPTED",
        "implementation_state": "IMPLEMENTED",
        "evidence_ids": ["EVID-TEST-0001"],
        "test_ids": ["TEST-JIRA-RECON-001"],
        "implementation_paths": ["src/module.py"],
        "jira_ids": ["PP-TASK-000999"],
    }
    write_jsonl(tmp_path / "plans/_traceability/requirements.jsonl", [requirement])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_module.py").write_text(
        "def test_module():\n    assert 1 == 1\n", encoding="utf-8"
    )
    write_json(
        tmp_path / "tests" / "TEST_CATALOG.json",
        {
            "schema_version": "2.0.0",
            "test_count": 1,
            "tests": [
                {
                    "test_id": "TEST-JIRA-RECON-001",
                    "path": "tests/test_module.py",
                    "callable": "test_module",
                }
            ],
        },
    )
    artifact = tmp_path / "evidence" / "receipt.txt"
    artifact.parent.mkdir()
    artifact.write_text("ok\n", encoding="utf-8")
    write_jsonl(
        tmp_path / "evidence" / "EVIDENCE_LEDGER.jsonl",
        [
            {
                "artifact_path": "evidence/receipt.txt",
                "claim": "pytest passed",
                "criterion_ids": ["AC-PP-000999-01"],
                "environment": "local_build_environment",
                "evidence_id": "EVID-TEST-0001",
                "method": "pytest",
                "observed_at_utc": "2026-08-18T00:00:00+00:00",
                "requirement_ids": ["REQ-TEST-0001"],
                "result": "PASS",
                "schema_version": "1.0.0",
                "sha256": sha256_canonical_file(artifact),
                "supersedes": None,
                "test_ids": ["TEST-JIRA-RECON-001"],
                "verification_status": "VERIFIED",
            }
        ],
    )
    issue = {
        "acceptance_criteria": [
            {
                "criterion_id": "AC-PP-000999-01",
                "statement": "Artifacts exist and tests pass.",
                "verification": {
                    "command": "pytest",
                    "method": "tests",
                    "path": "tests/test_module.py",
                    "status": "PLANNED",
                },
            }
        ],
        "blockers": [],
        "completion_evidence": [],
        "definition_of_done": ["Implementation complete.", "Tests pass."],
        "expected_implementation_artifacts": ["src/module.py"],
        "implementation_state": "PLANNED_ONLY",
        "issue_type": "TASK",
        "labels": ["planned"],
        "local_id": "PP-TASK-000999",
        "required_tests": ["TEST-JIRA-RECON-001"],
        "requirement_ids": ["REQ-TEST-0001"],
        "state": "BACKLOG",
        "title": "Implement the module",
    }
    done = {
        **issue,
        "local_id": "PP-TASK-000998",
        "state": "DONE",
        "implementation_state": "IMPLEMENTED",
        "completion_evidence": ["EVID-TEST-0001"],
        "title": "Already done",
    }
    for row in (issue, done):
        path = tmp_path / "jira" / "tasks" / f"{row['local_id']}.json"
        write_json(path, row)
    rebuild_jira_indexes(tmp_path)
    return {"task": tmp_path / "jira/tasks/PP-TASK-000999.json"}


def test_jira_reconciliation_applies_dod_and_never_reopens_done(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    ledger = evaluate_jira_implementation_reconciliation(tmp_path)
    by_id = {item["issue_id"]: item for item in ledger}
    assert by_id["PP-TASK-000999"]["accepted"] is True
    assert by_id["PP-TASK-000999"]["next_lifecycle_state"] == "DONE"
    assert by_id["PP-TASK-000998"]["accepted"] is False
    assert "already DONE" in by_id["PP-TASK-000998"]["reason"]
    result = apply_jira_implementation_reconciliation(tmp_path)
    assert result["applied_count"] == 1
    updated = read_json(paths["task"])
    assert updated["state"] == "DONE"
    assert updated["implementation_state"] == "IMPLEMENTED"
    assert updated["completion_evidence"] == ["EVID-TEST-0001"]
    assert updated["acceptance_criteria"][0]["verification"]["status"] == "VERIFIED"


def test_jira_reconciliation_rejects_missing_catalog_and_live_wording(tmp_path: Path) -> None:
    _seed(tmp_path)
    issue = read_json(tmp_path / "jira/tasks/PP-TASK-000999.json")
    issue["required_tests"] = ["TEST-MISSING"]
    write_json(tmp_path / "jira/tasks/PP-TASK-000999.json", issue)
    reason = evaluate_jira_implementation_reconciliation(tmp_path)[1]["reason"]
    assert "TEST_CATALOG" in reason
    issue["required_tests"] = ["TEST-JIRA-RECON-001"]
    issue["title"] = "Qualify live unattended Windows service"
    write_json(tmp_path / "jira/tasks/PP-TASK-000999.json", issue)
    row = next(
        item
        for item in evaluate_jira_implementation_reconciliation(tmp_path)
        if item["issue_id"] == "PP-TASK-000999"
    )
    assert row["accepted"] is True
    assert row["next_lifecycle_state"] is None
    assert row["next_implementation_state"] == "IMPLEMENTED"


def test_jira_implementation_reconcile_cli_requires_approve(tmp_path: Path, capsys) -> None:
    _seed(tmp_path)
    assert main(["jira-implementation-reconcile", "--root", str(tmp_path), "--apply"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "configuration_invalid"
    assert main(["jira-implementation-reconcile", "--root", str(tmp_path)]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["mode"] == "DRY_RUN"
    assert dry["ledger_count"] == 2


def test_bulk_script_ignores_base_ref_and_does_not_revert(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "bulk_reconcile_implemented_jira",
        ROOT / "scripts" / "bulk_reconcile_implemented_jira.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = _seed(tmp_path)
    original = read_json(paths["task"])
    result = module.reconcile(tmp_path, apply=False, base_ref="origin/main")
    assert result["schema_version"] == "2.0.0"
    assert "Historical --base-ref reverts" in result["rule"]
    assert read_json(paths["task"]) == original


def test_full_repository_jira_ledger_covers_every_issue() -> None:
    ledger = evaluate_jira_implementation_reconciliation(ROOT)
    issue_ids = {
        read_json(path)["local_id"]
        for directory in ("epics", "stories", "tasks", "subtasks", "bugs", "spikes")
        for path in (ROOT / "jira" / directory).glob("PP-*.json")
    }
    assert {item["issue_id"] for item in ledger} == issue_ids
    assert all("reason" in item and "accepted" in item for item in ledger)
