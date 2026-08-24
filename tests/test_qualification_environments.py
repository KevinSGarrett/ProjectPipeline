from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.assurance.qualification_environments import (
    compile_qualification_environments,
)
from project_pipeline.autonomy_runtime.campaign import REQUIRED_PP384_STAGES
from project_pipeline.validation.product_outcome import runtime_qualification_is_bound

ROOT = Path(__file__).resolve().parents[1]


def _identity(sha: str = "a" * 40, tree: str = "b" * 40, dirty: bool = False) -> dict:
    return {"sha": sha, "tree": tree, "dirty": dirty, "ok": True}


def _live(sha: str, tree: str, *, recovery_exit_code: int = 0) -> dict:
    stages = []
    for stage_id in REQUIRED_PP384_STAGES:
        observations = {}
        if stage_id == "windows_service_foreground":
            observations = {"recovery_exit_code": recovery_exit_code}
        stages.append(
            {
                "stage_id": stage_id,
                "outcome": "PASSED",
                "reasons": [],
                "observations": observations,
            }
        )
    return {
        "schema_version": "1.0.0",
        "bound_head": sha,
        "bound_tree": tree,
        "stages": stages,
    }


def test_compiler_rejects_ancestor_live_qualification(tmp_path: Path) -> None:
    report = compile_qualification_environments(
        tmp_path,
        identity=_identity(),
        live_qualification=_live("c" * 40, "d" * 40),
        unit_contract_probe=lambda: {"outcome": "PASSED"},
    )
    assert report["ok"] is False
    assert report["inherited_ancestor"] is True
    names = {item["environment"]: item["outcome"] for item in report["environments"]}
    assert names["deterministic_unit_and_contract"] == "PASSED"
    assert names["isolated_real_git_worktree_journey"] == "PASSED"
    assert names["local_real_integrated_journey"] == "FAILED"
    assert names["qualified_real_worker_provider_dispatch"] == "FAILED"
    assert "unattended_24_hour" in report["remaining_duration_or_release"]


def test_compiler_maps_matching_head_stages(tmp_path: Path) -> None:
    sha = "a" * 40
    tree = "b" * 40
    report = compile_qualification_environments(
        tmp_path,
        identity=_identity(sha, tree),
        live_qualification=_live(sha, tree),
        unit_contract_probe=lambda: {"outcome": "PASSED"},
    )
    assert report["ok"] is True
    assert report["bound_head"] == sha
    assert report["bound_tree"] == tree
    assert {item["environment"] for item in report["environments"]} == {
        "authorized_github_jira_sandbox_or_live",
        "deterministic_unit_and_contract",
        "isolated_real_git_worktree_journey",
        "local_real_integrated_journey",
        "qualified_real_worker_provider_dispatch",
        "recovery_and_restart",
        "windows_service_and_command_center",
    }
    assert all(item["outcome"] == "PASSED" for item in report["environments"])


def test_compiler_fails_closed_on_dirty_worktree(tmp_path: Path) -> None:
    report = compile_qualification_environments(
        tmp_path,
        identity=_identity(dirty=True),
        live_qualification=_live("a" * 40, "b" * 40),
        unit_contract_probe=lambda: {"outcome": "PASSED"},
    )
    assert report["ok"] is False
    names = {item["environment"]: item["outcome"] for item in report["environments"]}
    assert names["isolated_real_git_worktree_journey"] == "FAILED"


def test_compiler_loads_default_live_qualification_path(tmp_path: Path) -> None:
    sha = "a" * 40
    tree = "b" * 40
    live_dir = tmp_path / "evidence" / "autonomy_runtime" / "live_qualification"
    live_dir.mkdir(parents=True)
    (live_dir / "live_qualification_latest.json").write_text(
        json.dumps(_live(sha, tree)), encoding="utf-8"
    )
    report = compile_qualification_environments(
        tmp_path,
        identity=_identity(sha, tree),
        unit_contract_probe=lambda: {"outcome": "PASSED"},
    )
    assert report["ok"] is True
    assert report["inherited_ancestor"] is False


def test_compiler_uses_explicit_external_live_qualification_path(tmp_path: Path) -> None:
    sha = "a" * 40
    tree = "b" * 40
    external = tmp_path / "external-live.json"
    external.write_text(json.dumps(_live(sha, tree)), encoding="utf-8")
    report = compile_qualification_environments(
        tmp_path,
        identity=_identity(sha, tree),
        live_qualification_path=external,
        unit_contract_probe=lambda: {"outcome": "PASSED"},
    )
    assert report["ok"] is True
    assert report["inherited_ancestor"] is False


def test_compiler_fails_closed_on_live_qualification_path_escape(tmp_path: Path) -> None:
    sha = "a" * 40
    tree = "b" * 40
    outside = tmp_path.parent / "escaped-live.json"
    outside.write_text(json.dumps(_live(sha, tree)), encoding="utf-8")
    report = compile_qualification_environments(
        tmp_path,
        identity=_identity(sha, tree),
        live_qualification_path=outside,
        unit_contract_probe=lambda: {"outcome": "PASSED"},
    )
    assert report["ok"] is False
    names = {item["environment"]: item["observations"] for item in report["environments"]}
    assert names["local_real_integrated_journey"]["reason"] == "evidence_path_escape"


def test_runtime_qualification_rejects_ancestor_receipt_on_current_checkout() -> None:
    assert runtime_qualification_is_bound(ROOT) is False
