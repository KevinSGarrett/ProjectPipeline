from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from project_pipeline.io import sha256_file
from project_pipeline.resilience.gaps import evaluate_gpu_wait, simulate_provider_removal
from project_pipeline.resilience.restore import RestoreTargetPolicy
from project_pipeline.resilience.wip_preserve import (
    WipPreserveError,
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


def _restore_policy(tmp_path: Path, workspace: Path) -> RestoreTargetPolicy:
    return RestoreTargetPolicy([tmp_path], workspace_roots=[workspace])


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
    restored = restore_uncommitted_work(
        bundle,
        restored_root,
        apply=True,
        policy=_restore_policy(tmp_path, root),
        workspace_root=root,
    )
    assert restored["verified"] is True
    assert (restored_root / "tracked.txt").read_text(encoding="utf-8") == "dirty\n"
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "dirty\n"


def test_wip_restore_refuses_secret_and_digest_mismatch(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    digest_bundle = tmp_path / "digest-bundle"
    preserve_uncommitted_work(root, digest_bundle, apply=True)
    (digest_bundle / "files" / "tracked.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(WipPreserveError, match="digest mismatch"):
        restore_uncommitted_work(
            digest_bundle,
            tmp_path / "digest-restore",
            apply=True,
            policy=_restore_policy(tmp_path, root),
            workspace_root=root,
        )
    secret_bundle = tmp_path / "secret-bundle"
    preserve_uncommitted_work(root, secret_bundle, apply=True)
    secret_source = secret_bundle / "files" / ".env"
    secret_source.write_text("SECRET=1\n", encoding="utf-8")
    manifest_path = secret_bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"].append(
        {
            "path": ".env",
            "sha256": sha256_file(secret_source),
            "size_bytes": secret_source.stat().st_size,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(WipPreserveError, match="secret or traversal"):
        restore_uncommitted_work(
            secret_bundle,
            tmp_path / "secret-restore",
            apply=True,
            policy=_restore_policy(tmp_path, root),
            workspace_root=root,
        )


def test_wip_restore_rejects_unsafe_destination(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    bundle = tmp_path / "bundle"
    preserve_uncommitted_work(root, bundle, apply=True)
    policy = _restore_policy(tmp_path, root)
    filesystem_root = Path("C:/") if os.name == "nt" else Path("/")
    with pytest.raises(WipPreserveError):
        restore_uncommitted_work(
            bundle,
            filesystem_root,
            apply=False,
            policy=policy,
            workspace_root=root,
        )
    with pytest.raises(WipPreserveError):
        restore_uncommitted_work(
            bundle,
            tmp_path / "missing-policy",
            apply=True,
            workspace_root=root,
        )
    with pytest.raises(WipPreserveError):
        restore_uncommitted_work(
            bundle,
            root / ".git" / "wip-restore",
            apply=True,
            policy=policy,
            workspace_root=root,
        )
    protected = (
        Path(r"C:\Windows\Temp\pp-wip-restore") if os.name == "nt" else Path("/etc/pp-wip-restore")
    )
    with pytest.raises(WipPreserveError):
        restore_uncommitted_work(
            bundle,
            protected,
            apply=False,
            policy=policy,
            workspace_root=root,
        )
    if os.name == "nt":
        with pytest.raises(WipPreserveError):
            restore_uncommitted_work(
                bundle,
                Path(r"\\server\share\wip-restore"),
                apply=False,
                policy=policy,
                workspace_root=root,
            )
