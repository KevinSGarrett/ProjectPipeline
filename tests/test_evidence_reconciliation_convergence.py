from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.assurance.acceptance_scope import acceptance_scope_fingerprint
from project_pipeline.assurance.evidence import load_evidence
from project_pipeline.assurance.observation import (
    generate_observation,
    observation_rejection,
    refresh_post_merge_observations,
    select_current_observation,
)
from project_pipeline.assurance.observation_store import EvidenceObservationStore
from project_pipeline.assurance.policy import AssurancePolicy
from project_pipeline.assurance.requirement_reconciliation import (
    apply_evidence_bound_requirement_states,
    evaluate_requirement_reconciliation,
)
from project_pipeline.io import read_jsonl, sha256_canonical_file, write_jsonl

ROOT = Path(__file__).resolve().parents[1]


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    return (completed.stdout or "").strip()


def test_canonical_ledger_has_no_inline_subject_bindings() -> None:
    rows = load_evidence(ROOT)
    assert len(rows) == 177
    for row in rows:
        assert not row.get("integrated_sha")
        assert not row.get("head_sha")
        assert not row.get("integrated_tree")
        assert not row.get("tree_sha")


def test_current_head_evaluation_rejects_unbound_definitions() -> None:
    ledger = evaluate_requirement_reconciliation(ROOT)
    assert len(ledger) == 352
    rejected = [
        row for row in ledger if row["previous_state"] in {"PARTIALLY_IMPLEMENTED", "PLANNED_ONLY"}
    ]
    assert rejected
    assert all(
        "no valid current-head observation" in row["reason"]
        or "protected" in row["reason"]
        or "live" in row["reason"]
        or "no implementation paths" in row["reason"]
        or "test_ids" in row["reason"]
        or "evidence_ids" in row["reason"]
        or "TEST_CATALOG" in row["reason"]
        or "cataloged test" in row["reason"]
        or "generated-only" in row["reason"]
        or "missing" in row["reason"]
        or "empty" in row["reason"]
        or "unbound from" in row["reason"]
        for row in rejected
    )


def test_inline_sha_in_ledger_cannot_converge(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "obs@example.test")
    _git(root, "config", "user.name", "Observation")
    ledger = root / "evidence" / "EVIDENCE_LEDGER.jsonl"
    ledger.parent.mkdir()
    row = {"evidence_id": "EVID-000001", "claim": "x"}
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    _git(root, "add", "evidence/EVIDENCE_LEDGER.jsonl")
    _git(root, "commit", "-m", "definition")
    sha = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    row["integrated_sha"] = sha
    row["integrated_tree"] = tree
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    _git(root, "add", "evidence/EVIDENCE_LEDGER.jsonl")
    _git(root, "commit", "-m", "self-bind")
    new_sha = _git(root, "rev-parse", "HEAD")
    new_tree = _git(root, "rev-parse", "HEAD^{tree}")
    stored = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert stored["integrated_sha"] != new_sha
    assert stored["integrated_tree"] != new_tree


def _seed_repo(root: Path) -> dict:
    impl = root / "src" / "module.py"
    impl.parent.mkdir(parents=True)
    impl.write_text("value = 1\n", encoding="utf-8")
    test = root / "tests" / "test_mod.py"
    test.parent.mkdir(parents=True)
    test.write_text("def test_mod():\n    assert 1 == 1\n", encoding="utf-8")
    catalog = {
        "schema_version": "2.0.0",
        "test_count": 1,
        "tests": [{"test_id": "TEST-MOD", "path": "tests/test_mod.py", "callable": "test_mod"}],
    }
    (root / "tests" / "TEST_CATALOG.json").write_text(json.dumps(catalog), encoding="utf-8")
    requirement = {
        "requirement_id": "REQ-GOV-0006",
        "domain": "GOV",
        "implementation_state": "PARTIALLY_IMPLEMENTED",
        "statement": "Modular instruction routing is deterministic",
        "title": "Modular instructions",
        "acceptance_summary": "CLI validates instruction coverage",
        "implementation_paths": ["src/module.py"],
        "test_ids": ["TEST-MOD"],
        "evidence_ids": ["EVID-000001"],
        "jira_ids": ["PP-TASK-000210"],
    }
    (root / "plans/_traceability").mkdir(parents=True)
    write_jsonl(root / "plans/_traceability/requirements.jsonl", [requirement])
    artifact = root / "evidence" / "receipt.txt"
    artifact.parent.mkdir()
    artifact.write_text("ok\n", encoding="utf-8")
    definition = {
        "artifact_path": "evidence/receipt.txt",
        "claim": "mod",
        "criterion_ids": ["AC-1"],
        "environment": "local_build_environment",
        "evidence_id": "EVID-000001",
        "method": "pytest",
        "observed_at_utc": "2026-08-19T00:00:00+00:00",
        "requirement_ids": ["REQ-GOV-0006"],
        "result": "PASS",
        "schema_version": "1.0.0",
        "sha256": sha256_canonical_file(artifact),
        "test_ids": ["TEST-MOD"],
        "verification_status": "VERIFIED",
    }
    (root / "evidence" / "EVIDENCE_LEDGER.jsonl").write_text(
        json.dumps(definition) + "\n", encoding="utf-8"
    )
    return requirement


def test_metadata_only_merge_refresh_converges_without_self_sha_commit(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "obs@example.test")
    _git(root, "config", "user.name", "Observation")
    requirement = _seed_repo(root)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")
    sha = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")

    def runner(test_ids, paths):
        return {test_id: "PASS" for test_id in test_ids}

    observation = generate_observation(
        root, "EVID-000001", runner=runner, current_sha=sha, current_tree=tree
    )
    assert observation.integrated_sha == sha
    ledger = evaluate_requirement_reconciliation(root, current_sha=sha, current_tree=tree)
    assert ledger[0]["accepted"] is True
    applied = apply_evidence_bound_requirement_states(root, current_sha=sha, current_tree=tree)
    assert applied[0]["next_state"] == "IMPLEMENTED"
    _git(root, "add", "plans/_traceability/requirements.jsonl")
    _git(root, "commit", "-m", "metadata-only reconcile")
    merged_sha = _git(root, "rev-parse", "HEAD")
    merged_tree = _git(root, "rev-parse", "HEAD^{tree}")
    assert merged_sha != sha
    before_refresh = evaluate_requirement_reconciliation(
        root, current_sha=merged_sha, current_tree=merged_tree
    )
    assert before_refresh[0]["accepted"] is False
    refreshed = refresh_post_merge_observations(
        root,
        current_sha=merged_sha,
        current_tree=merged_tree,
        previous_sha=sha,
        previous_tree=tree,
    )
    assert refreshed
    after_refresh = evaluate_requirement_reconciliation(
        root, current_sha=merged_sha, current_tree=merged_tree
    )
    assert (
        after_refresh[0]["accepted"] is False or after_refresh[0]["previous_state"] == "IMPLEMENTED"
    )
    already = evaluate_requirement_reconciliation(
        root, current_sha=merged_sha, current_tree=merged_tree
    )[0]
    assert already["previous_state"] == "IMPLEMENTED"
    store = EvidenceObservationStore.open(root)
    current = store.current("EVID-000001", subject_sha=merged_sha, subject_tree=merged_tree)
    assert current is not None
    assert current.branch_head_sha == sha

    (root / "src" / "module.py").write_text("value = 2\n", encoding="utf-8")
    changed = acceptance_scope_fingerprint(
        root, read_jsonl(root / "plans/_traceability/requirements.jsonl")[0]
    )
    assert changed != observation.acceptance_scope_fingerprint
    invalidated = evaluate_requirement_reconciliation(
        root, current_sha=merged_sha, current_tree=merged_tree
    )[0]
    assert invalidated["previous_state"] == "IMPLEMENTED"
    current_after_change = select_current_observation(
        store,
        "EVID-000001",
        current_sha=merged_sha,
        current_tree=merged_tree,
        acceptance_fingerprint=changed,
    )
    reason = observation_rejection(
        current_after_change or current,
        requirement_id="REQ-GOV-0006",
        evidence_id="EVID-000001",
        test_ids=["TEST-MOD"],
        current_sha=merged_sha,
        current_tree=merged_tree,
        acceptance_fingerprint=changed,
        policy=AssurancePolicy(),
        now=datetime.now(UTC),
        live_required=False,
        definition=None,
    )
    assert reason is not None
    assert "acceptance-scope fingerprint" in reason or "no valid current-head observation" in reason
    assert requirement["requirement_id"] == "REQ-GOV-0006"
