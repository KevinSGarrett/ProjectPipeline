from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_pipeline.assurance.acceptance_scope import acceptance_scope_fingerprint
from project_pipeline.assurance.observation import record_observation
from project_pipeline.assurance.observation_store import EvidenceObservationStore
from project_pipeline.assurance.requirement_reconciliation import (
    apply_evidence_bound_requirement_states,
    contains_external_marker,
    evaluate_requirement_reconciliation,
    propose_evidence_bound_requirement_states,
)
from project_pipeline.cli import main
from project_pipeline.domain.evidence_observation import EnvironmentClass, ObservationResult
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
        and not contains_external_marker(
            " ".join(str(row.get(key, "")) for key in ("statement", "title", "acceptance_summary"))
        )
    )


def test_deliver_is_not_an_external_live_marker() -> None:
    assert contains_external_marker("Qualify live unattended Windows service")
    assert contains_external_marker("final Completion Gate")
    assert not contains_external_marker("Deliver the accepted requirements")
    assert not contains_external_marker("delivery progress and olive-colored UI")


def _seed_valid(
    tmp_path: Path, row: dict, *, evidence_updates: dict | None = None, record_obs: bool = True
) -> dict:
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
    if record_obs:
        store = EvidenceObservationStore.open(tmp_path)
        fingerprint = acceptance_scope_fingerprint(tmp_path, row)
        for evidence_id in row["evidence_ids"]:
            record_observation(
                store,
                evidence_id=evidence_id,
                test_ids=row["test_ids"],
                criterion_ids=["AC-TEST-01"],
                requirement_ids=[row["requirement_id"]],
                integrated_sha=CURRENT_SHA,
                integrated_tree=CURRENT_TREE,
                acceptance_scope_fingerprint=fingerprint,
                path_fingerprints={},
                artifact_digest=record["sha256"],
                command_identity=("pytest", "tests"),
                environment_class=EnvironmentClass.LOCAL,
                result=ObservationResult.PASS,
                independent_verification_receipt="test-seed",
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
    fail_space = tmp_path / "fail"
    fail_space.mkdir()
    _seed_valid(fail_space, dict(candidate))
    store = EvidenceObservationStore.open(fail_space)
    latest = store.latest_any(candidate["evidence_ids"][0])
    assert latest is not None
    record_observation(
        store,
        evidence_id=candidate["evidence_ids"][0],
        test_ids=candidate["test_ids"],
        criterion_ids=["AC-TEST-01"],
        requirement_ids=[candidate["requirement_id"]],
        integrated_sha=CURRENT_SHA,
        integrated_tree=CURRENT_TREE,
        acceptance_scope_fingerprint=latest.acceptance_scope_fingerprint,
        path_fingerprints={},
        artifact_digest=latest.artifact_digest,
        command_identity=("pytest", "fail"),
        environment_class=EnvironmentClass.LOCAL,
        result=ObservationResult.FAIL,
        independent_verification_receipt="fail",
    )
    assert (
        "records FAIL"
        in evaluate_requirement_reconciliation(
            fail_space, current_sha=CURRENT_SHA, current_tree=CURRENT_TREE
        )[0]["reason"]
    )
    stale_space = tmp_path / "stale"
    stale_space.mkdir()
    _seed_valid(stale_space, dict(candidate))
    stale_store = EvidenceObservationStore.open(stale_space)
    stale_latest = stale_store.latest_any(candidate["evidence_ids"][0])
    assert stale_latest is not None
    record_observation(
        stale_store,
        evidence_id=candidate["evidence_ids"][0],
        test_ids=candidate["test_ids"],
        criterion_ids=["AC-TEST-01"],
        requirement_ids=[candidate["requirement_id"]],
        integrated_sha=CURRENT_SHA,
        integrated_tree=CURRENT_TREE,
        acceptance_scope_fingerprint=stale_latest.acceptance_scope_fingerprint,
        path_fingerprints={},
        artifact_digest=stale_latest.artifact_digest,
        command_identity=("pytest", "stale"),
        environment_class=EnvironmentClass.LOCAL,
        result=ObservationResult.PASS,
        independent_verification_receipt="stale",
        now=datetime.now(UTC) - timedelta(days=40),
    )
    assert (
        "is stale"
        in evaluate_requirement_reconciliation(
            stale_space, current_sha=CURRENT_SHA, current_tree=CURRENT_TREE
        )[0]["reason"]
    )
    sha_space = tmp_path / "sha"
    sha_space.mkdir()
    _seed_valid(sha_space, dict(candidate))
    sha_store = EvidenceObservationStore.open(sha_space)
    sha_latest = sha_store.latest_any(candidate["evidence_ids"][0])
    assert sha_latest is not None
    record_observation(
        sha_store,
        evidence_id=candidate["evidence_ids"][0],
        test_ids=candidate["test_ids"],
        criterion_ids=["AC-TEST-01"],
        requirement_ids=[candidate["requirement_id"]],
        integrated_sha="a" * 40,
        integrated_tree=CURRENT_TREE,
        acceptance_scope_fingerprint=sha_latest.acceptance_scope_fingerprint,
        path_fingerprints={},
        artifact_digest=sha_latest.artifact_digest,
        command_identity=("pytest", "sha"),
        environment_class=EnvironmentClass.LOCAL,
        result=ObservationResult.PASS,
        independent_verification_receipt="sha",
    )
    assert (
        "no valid current-head observation"
        in evaluate_requirement_reconciliation(
            sha_space, current_sha=CURRENT_SHA, current_tree=CURRENT_TREE
        )[0]["reason"]
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
    unbound_space = tmp_path / "unbound"
    unbound_space.mkdir()
    _seed_valid(unbound_space, dict(candidate), record_obs=False)
    assert (
        "no valid current-head observation"
        in evaluate_requirement_reconciliation(
            unbound_space, current_sha=CURRENT_SHA, current_tree=CURRENT_TREE
        )[0]["reason"]
    )
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
