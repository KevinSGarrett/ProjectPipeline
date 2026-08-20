from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from project_pipeline.lifecycle.cycle_handoff import (
    validate_cycle_packet_integrity,
    write_cycle_packet_atomically,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _catalog_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    root = tmp_path / "git"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    catalog = root / "plans" / "_traceability" / "requirements_by_id.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps({"requirements": {"REQ-A": {"implementation_state": "PARTIALLY_IMPLEMENTED"}}})
        + "\n",
        encoding="utf-8",
    )
    _git(root, "add", "plans/_traceability/requirements_by_id.json")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    catalog.write_text(
        json.dumps({"requirements": {"REQ-A": {"implementation_state": "IMPLEMENTED"}}}) + "\n",
        encoding="utf-8",
    )
    _git(root, "add", "plans/_traceability/requirements_by_id.json")
    _git(root, "commit", "-m", "head")
    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    return root, base, head, tree


REQUIRED_BODY = """
Exact integrated main SHA abb9f8578fb41af4a51c769446e1caacd4769d30 tree 45587c78
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

MAIN = "abb9f8578fb41af4a51c769446e1caacd4769d30"
TREE = "45587c78a1604c47c176201ef84dd1b92201c475"


def _artifacts(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "DELIVERY_METER.json": {
            "main_sha": MAIN,
            "observed_at_utc": "2026-08-19T23:00:00Z",
        },
        "FRESH_DELIVERY_PROOF.json": {
            "main_sha": MAIN,
            "observed_at_utc": "2026-08-19T23:00:00Z",
        },
        "git_identity_verification.json": {"main_sha": MAIN, "tree": TREE},
        "validation_matrix.json": {"main_sha": MAIN},
        "front_status.json": {"main_sha": MAIN, "open_prs": []},
        "requirement_movement_ledger.json": {"main_sha": MAIN, "rows": [{"id": "REQ-1"}]},
        "jira_reconciliation_ledger.json": {"rows": [{"issue_id": "PP-TASK-000385"}]},
        "external_write_receipts.json": {"main_sha": MAIN, "receipts": [{"id": "JREC-1"}]},
        "campaign_reconciliation.json": {"status": "none"},
        "cleanup_inventory.json": {"main_sha": MAIN, "rows": []},
        "handoffs/Combined-Agent.md": REQUIRED_BODY,
    }
    payload.update(overrides)
    return payload


def _observation(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "origin_main": MAIN,
        "origin_main_tree": TREE,
        "compact_packet": {
            "origin_main_heads": [MAIN],
            "pull_requests": [],
            "worktrees": [],
            "recoverable_evidence_present": False,
            "stale_dependency_projection": False,
            "claims_floor_pass": False,
            "superseded_claims": ["cycle-14-accounting-correction"],
        },
        "github": {"open_pull_numbers": [], "remote_heads": ["main"]},
        "observed_remote_heads": ["main"],
        "live": {},
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, **overrides: object) -> Path:
    write_cycle_packet_atomically(tmp_path, _artifacts(**overrides))
    return tmp_path


def test_atomic_packet_from_one_observation_passes(tmp_path: Path) -> None:
    git_root, base, head, tree = _catalog_repo(tmp_path)
    packet = tmp_path / "packet"
    _write(
        packet,
        **{
            "DELIVERY_METER.json": {"main_sha": head, "observed_at_utc": "2026-08-19T23:00:00Z"},
            "FRESH_DELIVERY_PROOF.json": {
                "main_sha": head,
                "observed_at_utc": "2026-08-19T23:00:00Z",
            },
            "git_identity_verification.json": {"main_sha": head, "tree": tree},
            "validation_matrix.json": {"main_sha": head},
            "front_status.json": {"main_sha": head, "open_prs": []},
            "requirement_movement_ledger.json": {
                "main_sha": head,
                "base_sha": base,
                "head_sha": head,
                "head_tree": tree,
                "rows": [
                    {
                        "requirement_id": "REQ-A",
                        "before": "PARTIALLY_IMPLEMENTED",
                        "after": "IMPLEMENTED",
                    }
                ],
            },
            "external_write_receipts.json": {"main_sha": head, "receipts": [{"id": "JREC-1"}]},
            "cleanup_inventory.json": {"main_sha": head, "rows": []},
            "handoffs/Combined-Agent.md": REQUIRED_BODY + f"\nExact integrated main SHA {head}\n",
        },
    )
    result = validate_cycle_packet_integrity(
        directory=packet,
        observation=_observation(
            origin_main=head,
            origin_main_tree=tree,
            git_root=str(git_root),
            base_sha=base,
        ),
    )
    assert result["valid"] is True, result["findings"]
    sidecar = (packet / "handoffs" / "Combined-Agent.md.sha256").read_text(encoding="utf-8")
    assert sidecar.strip() == result["handoff_sha256"]


def test_nonempty_movement_ledger_without_catalog_derivation_fails(tmp_path: Path) -> None:
    _write(tmp_path)
    result = validate_cycle_packet_integrity(directory=tmp_path, observation=_observation())
    assert result["valid"] is False
    assert any("catalog-derived requirement movement" in item for item in result["findings"])


def test_packet_main_differs_from_fetched_remote_fails(tmp_path: Path) -> None:
    _write(tmp_path)
    result = validate_cycle_packet_integrity(
        directory=tmp_path,
        observation=_observation(origin_main="0" * 40),
    )
    assert any("freshly fetched remote main" in item for item in result["findings"])


def test_packet_timestamp_before_later_write_fails(tmp_path: Path) -> None:
    _write(tmp_path)
    result = validate_cycle_packet_integrity(
        directory=tmp_path,
        observation=_observation(latest_write_at_utc="2026-08-19T23:30:00Z"),
    )
    assert any("predates a later merge or Jira write" in item for item in result["findings"])


def test_sidecar_bytes_mismatch_fails(tmp_path: Path) -> None:
    _write(tmp_path)
    (tmp_path / "handoffs" / "Combined-Agent.md.sha256").write_text(
        "0" * 64 + "\n", encoding="utf-8"
    )
    result = validate_cycle_packet_integrity(directory=tmp_path, observation=_observation())
    assert any("sidecar differs from actual bytes" in item for item in result["findings"])


def test_ledgers_naming_different_heads_fail(tmp_path: Path) -> None:
    _write(
        tmp_path,
        **{"validation_matrix.json": {"main_sha": "1" * 40}},
    )
    result = validate_cycle_packet_integrity(directory=tmp_path, observation=_observation())
    assert any("different heads" in item for item in result["findings"])


def test_empty_ledgers_despite_observed_movements_fail(tmp_path: Path) -> None:
    _write(
        tmp_path,
        **{
            "requirement_movement_ledger.json": {"main_sha": MAIN, "rows": []},
            "external_write_receipts.json": {"main_sha": MAIN, "receipts": []},
        },
    )
    result = validate_cycle_packet_integrity(
        directory=tmp_path,
        observation=_observation(requirement_movements=True, external_writes=True),
    )
    assert any("empty despite observed movements/writes" in item for item in result["findings"])


def test_listed_pr_contradicts_github_fails(tmp_path: Path) -> None:
    _write(tmp_path)
    result = validate_cycle_packet_integrity(
        directory=tmp_path,
        observation=_observation(github={"open_pull_numbers": [80], "remote_heads": ["main"]}),
    )
    assert any("contradicts GitHub" in item for item in result["findings"])


def test_catalog_derived_noop_and_missing_movements_fail(tmp_path: Path) -> None:
    git_root, base, head, tree = _catalog_repo(tmp_path)
    packet = tmp_path / "packet"
    _write(
        packet,
        **{
            "DELIVERY_METER.json": {"main_sha": head, "observed_at_utc": "2026-08-20T00:00:00Z"},
            "FRESH_DELIVERY_PROOF.json": {
                "main_sha": head,
                "observed_at_utc": "2026-08-20T00:00:00Z",
            },
            "git_identity_verification.json": {"main_sha": head, "tree": tree},
            "validation_matrix.json": {"main_sha": head},
            "front_status.json": {"main_sha": head, "open_prs": []},
            "requirement_movement_ledger.json": {
                "main_sha": head,
                "base_sha": base,
                "head_sha": head,
                "head_tree": tree,
                "rows": [
                    {
                        "requirement_id": "REQ-A",
                        "before": "PARTIALLY_IMPLEMENTED",
                        "after": "PARTIALLY_IMPLEMENTED",
                    }
                ],
            },
            "external_write_receipts.json": {
                "main_sha": head,
                "receipts": [{"id": "R1", "pr": 80}],
            },
            "cleanup_inventory.json": {"main_sha": head, "rows": []},
            "handoffs/Combined-Agent.md": REQUIRED_BODY + f"\nExact integrated main SHA {head}\n",
        },
    )
    result = validate_cycle_packet_integrity(
        directory=packet,
        observation=_observation(
            origin_main=head,
            origin_main_tree=tree,
            git_root=str(git_root),
            base_sha=base,
            required_pr_numbers=[80, 81],
        ),
    )
    assert any("no-op" in item for item in result["findings"])
    assert any("missing requirement movement" in item for item in result["findings"])
    assert any("incomplete PR receipt range" in item for item in result["findings"])


def test_sidecar_written_before_payload_fails(tmp_path: Path) -> None:
    _write(tmp_path)
    payload = tmp_path / "handoffs" / "Combined-Agent.md"
    sidecar = tmp_path / "handoffs" / "Combined-Agent.md.sha256"
    payload.write_text(REQUIRED_BODY + "\nLater payload\n", encoding="utf-8")
    sidecar.touch()
    sidecar_stat = sidecar.stat()
    payload.touch()
    sidecar.chmod(sidecar.stat().st_mode)
    os.utime(sidecar, ns=(sidecar_stat.st_atime_ns, 1_000_000_000))
    os.utime(payload, ns=(sidecar_stat.st_atime_ns, 2_000_000_000))
    result = validate_cycle_packet_integrity(directory=tmp_path, observation=_observation())
    assert any("sidecar-written-before-payload" in item for item in result["findings"])


def test_live_jira_fact_contradicts_readback_fails(tmp_path: Path) -> None:
    _write(tmp_path)
    result = validate_cycle_packet_integrity(
        directory=tmp_path,
        observation=_observation(
            live={
                "packet_jira": {"To Do": 359, "In Progress": 14, "Done": 20},
                "observed_jira": {"To Do": 360, "In Progress": 13, "Done": 20},
            }
        ),
    )
    assert any("contradicts readback" in item for item in result["findings"])
