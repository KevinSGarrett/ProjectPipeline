from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from project_pipeline.release_hardening import (
    build_continuation_package,
    execute_local_post_deployment,
    validate_continuation_package,
)
from project_pipeline.release_hardening.post_deploy import (
    PostDeploymentObservation,
    verify_post_deployment,
)

ROOT = Path(__file__).resolve().parents[1]


def test_local_post_deployment_pipeline_cannot_finalize_on_incomplete_or_non_live() -> None:
    observation, decision = execute_local_post_deployment(
        ROOT, target_environment="local-worktree", live_target=False
    )
    assert all(observation.checks.values())
    assert decision.state == "BLOCKED_EXTERNAL"
    assert decision.live_target_verified is False
    live_without_evidence, live_decision = execute_local_post_deployment(
        ROOT, target_environment="local-worktree", live_target=True
    )
    assert live_without_evidence.live_target is True
    assert live_decision.state == "FAIL"
    assert "evidence" in " ".join(live_decision.reasons)


def test_post_deployment_incomplete_root_fails_closed(tmp_path: Path) -> None:
    observation, decision = execute_local_post_deployment(
        tmp_path, target_environment="broken", live_target=False
    )
    assert observation.checks["health"] is False
    assert observation.checks["integration"] is False
    assert decision.state == "FAIL"
    assert decision.missing_or_failed_checks


def test_continuation_package_from_detached_head_without_default_branch(tmp_path: Path) -> None:
    repo = tmp_path / "detached"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "cont@example.test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Continuation"],
        check=True,
        capture_output=True,
    )
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    (repo / "plans" / "_traceability").mkdir(parents=True)
    (repo / "plans" / "_traceability" / "requirements.jsonl").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "--detach", "HEAD"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "branch", "-D", "main"], check=True, capture_output=True
    )
    package = build_continuation_package(repo)
    assert package["branch"] is None
    assert package["user_action_required"] is False
    assert len(package["source_sha"]) == 40
    assert len(package["source_tree"]) == 40
    assert validate_continuation_package(package) == []


def test_continuation_package_rejects_control_characters_and_abbreviated_git_ids() -> None:
    package = build_continuation_package(ROOT)
    assert package["user_action_required"] is False
    assert package["depends_on_chat_history"] is False
    assert len(package["source_sha"]) == 40
    assert len(package["source_tree"]) == 40
    assert validate_continuation_package(package) == []
    broken = dict(package)
    broken["source_sha"] = package["source_sha"][:12]
    broken["note"] = "HUMAN_REQUIRED\x07"
    errors = validate_continuation_package(broken)
    assert any("40-hex" in item for item in errors)
    assert any("control" in item for item in errors)
    assert any("HUMAN_REQUIRED" in item for item in errors)


def test_verify_post_deployment_still_requires_every_named_check() -> None:
    names = (
        "health",
        "version",
        "migration",
        "integration",
        "security",
        "telemetry",
        "golden_journey",
    )
    decision = verify_post_deployment(
        PostDeploymentObservation(
            target_environment="staging",
            checks={name: True for name in names if name != "telemetry"},
        )
    )
    assert decision.state == "FAIL"
    assert "telemetry" in decision.missing_or_failed_checks
    serialized = json.dumps(decision.model_dump(mode="json"))
    assert "\x00" not in serialized


def test_release_hardening_cli_grammar_emits_candidate_and_continuation() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    candidate = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_pipeline",
            "release-hardening",
            "candidate",
            "--root",
            str(ROOT),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert candidate.returncode == 0, candidate.stderr
    payload = json.loads(candidate.stdout)
    assert payload["release_candidate"]["source_sha"]
    assert len(payload["release_candidate"]["source_sha"]) == 40
    continuation = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_pipeline",
            "release-hardening",
            "continuation",
            "--root",
            str(ROOT),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert continuation.returncode == 0, continuation.stderr
    package = json.loads(continuation.stdout)["continuation_package"]
    assert package["user_action_required"] is False
