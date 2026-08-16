from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from project_pipeline.assurance.delivery_progress import (
    calculate_progress_delta,
    evaluate_delivery_gate,
)
from project_pipeline.domain.assurance import DeliveryGateState


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _issue(local_id: str, *, complete: bool = False) -> dict[str, object]:
    return {
        "local_id": local_id,
        "issue_type": "TASK",
        "state": "MERGE_READY" if complete else "BACKLOG",
        "implementation_state": "IMPLEMENTED" if complete else "PLANNED_ONLY",
        "labels": ["assurance", "implemented"] if complete else ["assurance"],
        "completion_evidence": [f"EVID-{local_id[-6:]}"] if complete else [],
        "acceptance_criteria": [
            {
                "criterion_id": f"AC-{local_id}",
                "statement": "The bounded behavior is verified.",
                "verification": {
                    "method": "automated",
                    "status": "VERIFIED" if complete else "PLANNED",
                },
            }
        ],
        "requirement_ids": ["REQ-ASSURE-0008"],
        "owner_required_capability": "execution_assurance",
        "expected_implementation_artifacts": [
            "src/project_pipeline/feature.py",
        ],
        "required_tests": ["TEST-FEATURE-001"],
    }


def _repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    issue_path = root / "jira" / "tasks" / "PP-TASK-000001.json"
    _write_json(issue_path, _issue("PP-TASK-000001"))
    _write_json(
        root / "tests" / "TEST_CATALOG.json",
        {
            "schema_version": "2.0.0",
            "test_count": 1,
            "tests": [
                {
                    "callable": "test_feature",
                    "path": "tests/test_feature.py",
                    "test_id": "TEST-FEATURE-001",
                }
            ],
        },
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD")


def test_progress_delta_does_not_count_lifecycle_activity() -> None:
    delta = calculate_progress_delta(
        before={
            "implemented_requirements": 10,
            "verified_criteria": 5,
            "blockers": 2,
            "failures": 0,
            "verified_evidence": 4,
            "integrated_changes": 3,
        },
        after={
            "implemented_requirements": 10,
            "verified_criteria": 5,
            "blockers": 2,
            "failures": 0,
            "verified_evidence": 4,
            "integrated_changes": 3,
        },
        activity_units=12,
        administrative_units=12,
    )

    assert delta.progress_units == 0
    assert not delta.meaningful_progress
    assert delta.administrative_ratio_milli == 1000
    assert delta.noncritical_administrative_ratio_milli == 1000


def test_single_item_lifecycle_only_delivery_is_blocked(tmp_path: Path) -> None:
    root, base = _repository(tmp_path)
    _write_json(
        root / "jira" / "tasks" / "PP-TASK-000001.json",
        _issue("PP-TASK-000001", complete=True),
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "advance status")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.BLOCKED
    assert decision.lifecycle_only_task_ids == ("PP-TASK-000001",)
    assert "lifecycle transitions" in decision.reasons[0]


@pytest.mark.parametrize(
    ("extra_path", "content"),
    [
        ("README.md", "harmless documentation\n"),
        ("config/harmless.json", "{}\n"),
        ("tests/test_harmless.py", "def test_harmless():\n    assert 1 == 1\n"),
    ],
)
def test_harmless_file_cannot_disguise_single_lifecycle_transition(
    tmp_path: Path, extra_path: str, content: str
) -> None:
    root, base = _repository(tmp_path)
    _write_json(
        root / "jira" / "tasks" / "PP-TASK-000001.json",
        _issue("PP-TASK-000001", complete=True),
    )
    extra = root / extra_path
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text(content, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "disguise lifecycle transition")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.BLOCKED
    assert decision.lifecycle_only_task_ids == ("PP-TASK-000001",)
    assert "unrelated churn" in decision.reasons[0]


def test_unrelated_source_and_test_cannot_disguise_lifecycle_transition(
    tmp_path: Path,
) -> None:
    root, base = _repository(tmp_path)
    _write_json(
        root / "jira" / "tasks" / "PP-TASK-000001.json",
        _issue("PP-TASK-000001", complete=True),
    )
    source = root / "src" / "unrelated.py"
    test = root / "tests" / "test_unrelated.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    test.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    test.write_text("def test_unrelated():\n    assert 1 == 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add unrelated churn beside lifecycle transition")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.BLOCKED
    assert decision.lifecycle_only_task_ids == ("PP-TASK-000001",)
    assert "unrelated churn" in decision.reasons[0]


def test_issue_bound_implementation_and_required_test_allow_transition(
    tmp_path: Path,
) -> None:
    root, base = _repository(tmp_path)
    _write_json(
        root / "jira" / "tasks" / "PP-TASK-000001.json",
        _issue("PP-TASK-000001", complete=True),
    )
    source = root / "src" / "project_pipeline" / "feature.py"
    test = root / "tests" / "test_feature.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    test.write_text("def test_feature():\n    assert 1 == 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "implement issue-bound behavior")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.PASS
    assert decision.objective_progress_units >= 1


def test_material_governance_correction_is_objective_progress(tmp_path: Path) -> None:
    root, base = _repository(tmp_path)
    policy = root / "instructions" / "11_POLICY.md"
    config = root / "config" / "policy.json"
    manifest = root / "instructions" / "INSTRUCTION_MANIFEST.json"
    test = root / "tests" / "test_instruction_system.py"
    policy.parent.mkdir(parents=True, exist_ok=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("# Corrected policy\n", encoding="utf-8")
    _write_json(config, {"enabled": True})
    _write_json(manifest, {"schema_version": "1.0.0", "managed_files": []})
    test.write_text("def test_policy():\n    assert 1 == 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "correct governed policy")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.PASS
    assert decision.objective_progress_units == 1
    assert not decision.lifecycle_only_task_ids


def test_total_and_noncritical_administration_are_reported_separately(
    tmp_path: Path,
) -> None:
    root, base = _repository(tmp_path)
    _write_json(
        root / "jira" / "tasks" / "PP-TASK-000001.json",
        _issue("PP-TASK-000001", complete=True),
    )
    source = root / "src" / "project_pipeline" / "feature.py"
    test = root / "tests" / "test_feature.py"
    generated = root / "jira" / "indexes" / "issues.jsonl"
    generated_instruction_manifest = root / "instructions" / "INSTRUCTION_MANIFEST.json"
    generated_schema = root / "schemas" / "feature.schema.json"
    generated_traceability = root / "plans" / "_traceability" / "requirements.jsonl"
    generated_evidence_summary = root / "evidence" / "EVIDENCE_SUMMARY.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    generated.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    test.write_text("def test_feature():\n    assert 1 == 1\n", encoding="utf-8")
    generated.write_text("{}\n", encoding="utf-8")
    _write_json(generated_instruction_manifest, {"managed_files": []})
    _write_json(generated_schema, {"type": "object"})
    generated_traceability.parent.mkdir(parents=True, exist_ok=True)
    generated_traceability.write_text("{}\n", encoding="utf-8")
    _write_json(generated_evidence_summary, {"evidence_count": 0})
    _git(root, "add", ".")
    _git(root, "commit", "-m", "deliver with required projection")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.PASS
    assert decision.administrative_units == 6
    assert decision.noncritical_administrative_units == 1
    assert decision.administrative_ratio_milli == 750
    assert decision.noncritical_administrative_ratio_milli == 125


def test_evidence_backed_reconciliation_requires_a_real_batch(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    for number in range(1, 4):
        local_id = f"PP-TASK-{number:06d}"
        _write_json(root / "jira" / "tasks" / f"{local_id}.json", _issue(local_id))
    _git(root, "add", ".")
    _git(root, "commit", "-m", "establish batch base")
    base = _git(root, "rev-parse", "HEAD")
    for number in range(1, 4):
        local_id = f"PP-TASK-{number:06d}"
        _write_json(
            root / "jira" / "tasks" / f"{local_id}.json",
            _issue(local_id, complete=True),
        )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "reconcile completed batch")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.PASS
    assert decision.reconciliation_batch
    assert len(decision.lifecycle_only_task_ids) == 3


def test_unrelated_completed_items_do_not_form_a_reconciliation_batch(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    for number in range(1, 4):
        local_id = f"PP-TASK-{number:06d}"
        _write_json(root / "jira" / "tasks" / f"{local_id}.json", _issue(local_id))
    _git(root, "add", ".")
    _git(root, "commit", "-m", "establish incompatible base")
    base = _git(root, "rev-parse", "HEAD")
    for number in range(1, 4):
        local_id = f"PP-TASK-{number:06d}"
        issue = _issue(local_id, complete=True)
        if number == 3:
            issue["owner_required_capability"] = "unrelated_capability"
            issue["labels"] = ["unrelated", "implemented"]
        _write_json(root / "jira" / "tasks" / f"{local_id}.json", issue)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "mix unrelated lifecycle items")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.BLOCKED
    assert not decision.reconciliation_batch
    assert len(decision.lifecycle_only_task_ids) == 3


def test_implementation_and_test_change_is_objective_progress(tmp_path: Path) -> None:
    root, base = _repository(tmp_path)
    source = root / "src" / "project_pipeline" / "feature.py"
    test = root / "tests" / "test_feature.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    test.write_text("def test_value():\n    assert 1 == 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "implement accepted behavior")

    decision = evaluate_delivery_gate(root, base_ref=base)

    assert decision.state is DeliveryGateState.PASS
    assert decision.objective_progress_units == 1
    assert not decision.reconciliation_batch
