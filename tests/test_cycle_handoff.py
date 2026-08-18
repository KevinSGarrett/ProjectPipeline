from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.lifecycle.cycle_handoff import validate_cycle_handoff

REQUIRED_BODY = """
Exact integrated main SHA 295058e tree abc timestamp 2026-08-18T00:00:00Z
Open PR count 0 remote branch count 0 worktree count 1
Accepted commits fronts and slices with proof
Jira local/live reconciliation table
PP-384 live stage table
PP-385 run state heartbeat
Completion Gate INCOMPLETE unmet predicates listed
External precondition cursor-cli with autonomous recheck
Superseded Cycle 10 claims
Next autonomous action owned by the combined agent
"""


def _packet(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "origin_main_heads": ["295058e2bb60973c5d62d23457efabe2e50d4ed1"],
        "pull_requests": [],
        "worktrees": [],
        "recoverable_evidence_present": False,
        "stale_dependency_projection": False,
        "claims_floor_pass": False,
        "superseded_claims": [],
    }
    payload.update(overrides)
    return payload


def test_valid_compact_handoff_packet_passes(tmp_path: Path) -> None:
    result = validate_cycle_handoff(
        handoff_text=REQUIRED_BODY,
        meter={"cycle": 11},
        proof={"baseline_sha": "295058e2bb60973c5d62d23457efabe2e50d4ed1"},
        packet=_packet(worktrees=[{"path": str(tmp_path), "status": "active"}]),
    )
    assert result["valid"] is True
    assert result["findings"] == []


def test_rejects_contradictory_main_heads_without_supersession() -> None:
    result = validate_cycle_handoff(
        handoff_text=REQUIRED_BODY,
        meter={"cycle": 11},
        proof={"baseline_sha": "a"},
        packet=_packet(origin_main_heads=["aaa", "bbb"], superseded_claims=[]),
    )
    assert result["valid"] is False
    assert any("contradictory origin/main" in item for item in result["findings"])


def test_rejects_pr_labeled_open_and_merged() -> None:
    result = validate_cycle_handoff(
        handoff_text=REQUIRED_BODY,
        meter={"cycle": 11},
        proof={"baseline_sha": "a"},
        packet=_packet(pull_requests=[{"number": 55, "open": True, "merged": True}]),
    )
    assert any("open and merged" in item for item in result["findings"])


def test_rejects_deleted_worktree_labeled_active(tmp_path: Path) -> None:
    result = validate_cycle_handoff(
        handoff_text=REQUIRED_BODY,
        meter={"cycle": 11},
        proof={"baseline_sha": "a"},
        packet=_packet(worktrees=[{"path": str(tmp_path / "missing"), "status": "active"}]),
    )
    assert any("deleted worktree labeled active" in item for item in result["findings"])


def test_rejects_nothing_left_when_recoverable_evidence_exists() -> None:
    result = validate_cycle_handoff(
        handoff_text=REQUIRED_BODY + "\nNothing else to implement.\n",
        meter={"cycle": 11},
        proof={"baseline_sha": "a"},
        packet=_packet(recoverable_evidence_present=True),
    )
    assert any("recoverable evidence" in item for item in result["findings"])


def test_rejects_missing_meter_and_human_assignment() -> None:
    result = validate_cycle_handoff(
        handoff_text=REQUIRED_BODY + "\nThe user should execute `pytest -q` next.\n",
        meter={},
        proof={"baseline_sha": "a"},
        packet=_packet(),
    )
    assert any("missing delivery meter" in item for item in result["findings"])
    assert any("exact command as work for a person" in item for item in result["findings"])


def test_rejects_floor_pass_without_script_success() -> None:
    result = validate_cycle_handoff(
        handoff_text=REQUIRED_BODY,
        meter={"cycle": 11},
        proof={"baseline_sha": "a"},
        packet=_packet(claims_floor_pass=True),
        floor_script_ran=False,
    )
    assert any("Assert-CycleFloor.ps1" in item for item in result["findings"])


def test_cli_validate_rejects_missing_packet(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff.md"
    meter = tmp_path / "meter.json"
    proof = tmp_path / "proof.json"
    handoff.write_text(REQUIRED_BODY, encoding="utf-8")
    meter.write_text(json.dumps({"cycle": 11}), encoding="utf-8")
    proof.write_text(json.dumps({"baseline_sha": "a"}), encoding="utf-8")
    code = main(
        [
            "cycle-handoff",
            "validate",
            "--handoff",
            str(handoff),
            "--meter",
            str(meter),
            "--proof",
            str(proof),
            "--packet",
            str(tmp_path / "missing.json"),
        ]
    )
    assert code == 1


def test_rejects_user_visible_human_required_phrase() -> None:
    result = validate_cycle_handoff(
        handoff_text=REQUIRED_BODY + "\nRoute is HUMAN_REQUIRED\n",
        meter={"cycle": 11},
        proof={"baseline_sha": "a"},
        packet=_packet(),
    )
    assert any("HUMAN_REQUIRED" in item for item in result["findings"])
