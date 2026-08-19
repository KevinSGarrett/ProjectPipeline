from __future__ import annotations

import subprocess
from pathlib import Path

from project_pipeline.resilience.gaps import evaluate_gpu_wait, simulate_provider_removal
from project_pipeline.resilience.wip_preserve import (
    preserve_uncommitted_work,
    restore_uncommitted_work,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "gaps@example.test")
    _git(root, "config", "user.name", "Resilience Gaps")
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "init")
    return root


def test_provider_removal_is_isolated_and_substitutes_local() -> None:
    decision = simulate_provider_removal(
        provider_id="cloud-a",
        required_capabilities=("reasoning",),
        providers=(
            {
                "provider_id": "cloud-a",
                "available": True,
                "capabilities": ["reasoning"],
                "cost_score": 9,
            },
            {
                "provider_id": "local",
                "available": True,
                "capabilities": ["reasoning"],
                "cost_score": 0,
            },
        ),
    )
    assert decision.isolated is True
    assert decision.live_mutation_performed is False
    assert decision.selected_substitute == "local"
    assert decision.task_semantics_preserved is True
    assert decision.user_action_required is False


def test_gpu_wait_does_not_block_independent_lanes() -> None:
    decision = evaluate_gpu_wait(
        [
            {"task_id": "PP-TASK-GPU", "gpu_required": True},
            {"task_id": "PP-TASK-CPU", "gpu_required": False},
        ]
    )
    assert decision.gpu_dependent_state == "WAITING_RESOURCES"
    assert decision.independent_lanes_continue is True
    assert decision.waiting_task_ids == ("PP-TASK-GPU",)
    assert decision.continuing_task_ids == ("PP-TASK-CPU",)
    assert decision.recheck_owned is True


def test_wip_preserve_and_restore_round_trip(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    bundle = tmp_path / "bundle"
    preserved = preserve_uncommitted_work(root, bundle, apply=True)
    assert preserved["preserved"] is True
    restored_root = tmp_path / "restored"
    restored = restore_uncommitted_work(bundle, restored_root, apply=True)
    assert restored["verified"] is True
    assert (restored_root / "tracked.txt").read_text(encoding="utf-8") == "dirty\n"
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "dirty\n"
