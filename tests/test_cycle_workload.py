from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from project_pipeline.assurance.cycle_workload import (
    derive_requirement_movements,
    evaluate_cycle_workload,
    load_cycle_workload_policy,
    validate_requirement_movement_ledger,
)
from project_pipeline.assurance.policy import CycleWorkloadPolicy
from project_pipeline.cli import main


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


def _catalog(states: dict[str, str]) -> dict[str, object]:
    return {
        "requirements": {
            requirement_id: {"implementation_state": state}
            for requirement_id, state in states.items()
        }
    }


def _repo(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _write_json(
        root / "plans" / "_traceability" / "requirements_by_id.json",
        _catalog(
            {
                "REQ-A": "PARTIALLY_IMPLEMENTED",
                "REQ-B": "PLANNED_ONLY",
                "REQ-C": "IMPLEMENTED",
            }
        ),
    )
    _git(root, "add", "plans/_traceability/requirements_by_id.json")
    _git(root, "commit", "-m", "base catalog")
    base = _git(root, "rev-parse", "HEAD")
    _write_json(
        root / "plans" / "_traceability" / "requirements_by_id.json",
        _catalog(
            {
                "REQ-A": "IMPLEMENTED",
                "REQ-B": "PARTIALLY_IMPLEMENTED",
                "REQ-C": "IMPLEMENTED",
            }
        ),
    )
    _git(root, "add", "plans/_traceability/requirements_by_id.json")
    _git(root, "commit", "-m", "head catalog")
    head = _git(root, "rev-parse", "HEAD")
    return root, base, head


def _unit(unit_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "unit_id": unit_id,
        "acceptance_boundary": f"boundary-{unit_id}",
        "requirement_id": "REQ-A",
        "criterion_id": "AC-1",
        "falsifier": "multiprocess contention fails closed",
        "before_behavior": "race",
        "after_behavior": "atomic admit",
        "production_paths": ["src/project_pipeline/persistence/migrations.py"],
        "tests": ["tests/test_migrations.py"],
        "integrated_sha": "pending",
        "integrated_tree": "pending",
        "rollback_boundary": f"rollback-{unit_id}",
        "deduplication_identity": f"dedup-{unit_id}",
        "weight": 3,
        "counts_as_substantive": True,
    }
    payload.update(overrides)
    return payload


def test_policy_rejects_non_doubled_minimum() -> None:
    with pytest.raises(ValidationError):
        CycleWorkloadPolicy(minimum_score=47)


def test_derive_requirement_movements(tmp_path: Path) -> None:
    root, base, head = _repo(tmp_path)
    movements = derive_requirement_movements(root, base_ref=base, head_ref=head)
    assert [(item.requirement_id, item.before, item.after) for item in movements] == [
        ("REQ-A", "PARTIALLY_IMPLEMENTED", "IMPLEMENTED"),
        ("REQ-B", "PLANNED_ONLY", "PARTIALLY_IMPLEMENTED"),
    ]


def test_rejects_noop_missing_extra_and_wrong_states(tmp_path: Path) -> None:
    root, base, head = _repo(tmp_path)
    expected = derive_requirement_movements(root, base_ref=base, head_ref=head)
    findings = validate_requirement_movement_ledger(
        {
            "rows": [
                {
                    "requirement_id": "REQ-A",
                    "before": "IMPLEMENTED",
                    "after": "IMPLEMENTED",
                },
                {
                    "requirement_id": "REQ-B",
                    "before": "PARTIALLY_IMPLEMENTED",
                    "after": "IMPLEMENTED",
                },
                {
                    "requirement_id": "REQ-Z",
                    "before": "PLANNED_ONLY",
                    "after": "IMPLEMENTED",
                },
            ]
        },
        expected,
    )
    codes = {item.code for item in findings}
    assert "MOVEMENT_NOOP" in codes
    assert "MOVEMENT_MISSING" in codes
    assert "MOVEMENT_EXTRA" in codes
    assert "MOVEMENT_WRONG_BEFORE" in codes
    assert "MOVEMENT_WRONG_AFTER" in codes


def test_duplicate_unit_and_identical_rollback_are_rejected(tmp_path: Path) -> None:
    root, base, head = _repo(tmp_path)
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    decision = evaluate_cycle_workload(
        root=root,
        policy=CycleWorkloadPolicy(),
        ledger={
            "base_sha": base,
            "head_sha": head,
            "head_tree": tree,
            "units": [
                _unit("C16-A", integrated_sha=head, integrated_tree=tree),
                _unit("C16-A", integrated_sha=head, integrated_tree=tree),
                _unit(
                    "C16-B",
                    integrated_sha=head,
                    integrated_tree=tree,
                    rollback_boundary="rollback-C16-A",
                    deduplication_identity="dedup-C16-A",
                    acceptance_boundary="boundary-C16-A",
                ),
            ],
        },
        requirement_ledger={
            "rows": [
                {
                    "requirement_id": "REQ-A",
                    "before": "PARTIALLY_IMPLEMENTED",
                    "after": "IMPLEMENTED",
                },
                {
                    "requirement_id": "REQ-B",
                    "before": "PLANNED_ONLY",
                    "after": "PARTIALLY_IMPLEMENTED",
                },
            ]
        },
        base_ref=base,
        head_ref=head,
    )
    codes = {item.code for item in decision.findings}
    assert "DUPLICATE_UNIT" in codes
    assert "IDENTICAL_ROLLBACK" in codes


def test_bookkeeping_and_dependency_install_earn_zero(tmp_path: Path) -> None:
    root, base, head = _repo(tmp_path)
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    decision = evaluate_cycle_workload(
        root=root,
        policy=CycleWorkloadPolicy(),
        ledger={
            "base_sha": base,
            "head_sha": head,
            "head_tree": tree,
            "administrative_credit": 2,
            "units": [
                _unit(
                    "C16-BOOK",
                    category="bookkeeping",
                    counts_as_substantive=True,
                    integrated_sha=head,
                    integrated_tree=tree,
                ),
                _unit(
                    "C16-DEP",
                    category="dependency_install",
                    counts_as_substantive=True,
                    integrated_sha=head,
                    integrated_tree=tree,
                ),
            ],
        },
        requirement_ledger={"rows": []},
        base_ref=base,
        head_ref=head,
    )
    codes = {item.code for item in decision.findings}
    assert "ADMINISTRATIVE_CREDIT" in codes
    assert "DEPENDENCY_INSTALL_CREDIT" in codes
    assert decision.weighted_score == 0


def test_incomplete_evidence_and_wrong_head_are_rejected(tmp_path: Path) -> None:
    root, base, head = _repo(tmp_path)
    decision = evaluate_cycle_workload(
        root=root,
        policy=CycleWorkloadPolicy(),
        ledger={
            "base_sha": "0" * 40,
            "head_sha": "1" * 40,
            "head_tree": "2" * 40,
            "units": [{"unit_id": "C16-X", "weight": 2, "counts_as_substantive": True}],
        },
        requirement_ledger={"rows": []},
        base_ref=base,
        head_ref=head,
    )
    codes = {item.code for item in decision.findings}
    assert "INCOMPLETE_EVIDENCE" in codes
    assert "WRONG_BASE" in codes
    assert "WRONG_HEAD" in codes
    assert "CONTRADICTORY_TREE" in codes


def test_endgame_saturation_requires_complete_gate(tmp_path: Path) -> None:
    root, base, head = _repo(tmp_path)
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    decision = evaluate_cycle_workload(
        root=root,
        policy=CycleWorkloadPolicy(),
        ledger={
            "base_sha": base,
            "head_sha": head,
            "head_tree": tree,
            "endgame_saturation": True,
            "completion_gate_complete": False,
            "units": [
                _unit("C16-ONE", integrated_sha=head, integrated_tree=tree),
            ],
        },
        requirement_ledger={
            "rows": [
                {
                    "requirement_id": "REQ-A",
                    "before": "PARTIALLY_IMPLEMENTED",
                    "after": "IMPLEMENTED",
                },
                {
                    "requirement_id": "REQ-B",
                    "before": "PLANNED_ONLY",
                    "after": "PARTIALLY_IMPLEMENTED",
                },
            ]
        },
        base_ref=base,
        head_ref=head,
    )
    codes = {item.code for item in decision.findings}
    assert "ENDGAME_SATURATION_INCOMPLETE" in codes


def test_cli_reads_policy(tmp_path: Path) -> None:
    root, _, _ = _repo(tmp_path)
    _write_json(
        root / "config" / "assurance_policy.json",
        json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "assurance_policy.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    code = main(["assurance", "cycle-workload", "--root", str(root)])
    assert code == 0
    policy = load_cycle_workload_policy(root)
    assert policy.minimum_score == 48
    assert policy.minimum_units == 14
    assert policy.non_compounding is True
