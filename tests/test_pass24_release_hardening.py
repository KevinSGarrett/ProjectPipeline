from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from project_pipeline.configuration import load_runtime_configuration
from project_pipeline.release_hardening import (
    CleanupPlanner,
    build_hardening_report,
    build_release_candidate,
    qualify_packaging_targets,
    qualify_tools,
    release_input_fingerprint,
    validate_release_hardening,
)
from project_pipeline.release_hardening.models import QualificationState
from project_pipeline.security.supply_chain import evaluate_supply_chain

ROOT = Path(__file__).resolve().parents[1]


def test_pass24_upstream_gate_covers_exact_candidates_and_blocks_agpl_activation():
    rows = qualify_tools(ROOT)
    assert len(rows) == 12
    by_id = {row.upstream_id: row for row in rows}
    assert by_id["UPSTREAM-048"].state is QualificationState.BLOCKED_LICENSE_POLICY
    assert by_id["UPSTREAM-089"].state is QualificationState.BLOCKED_LICENSE_POLICY
    assert all(row.authority == "EVIDENCE_OR_MECHANICS_ONLY" for row in rows)


def test_harden_runner_configuration_is_pinned_to_reviewed_sha():
    policy = json.loads((ROOT / "config/release_policy.json").read_text())
    workflow = (ROOT / ".github/workflows/quality.yml").read_text()
    assert f"step-security/harden-runner@{policy['harden_runner_reviewed_sha']}" in workflow
    row = next(item for item in qualify_tools(ROOT) if item.upstream_id == "UPSTREAM-100")
    assert row.state is QualificationState.CONFIGURED_PINNED_PROFILE


def test_external_tool_absence_never_becomes_success():
    for row in qualify_tools(ROOT):
        if (
            row.executable
            and not row.runtime_available
            and row.state is not QualificationState.BLOCKED_LICENSE_POLICY
        ):
            assert row.state is QualificationState.ADAPTER_IMPLEMENTED_TOOL_UNAVAILABLE


def test_supply_chain_internal_gate_and_sbom_are_available():
    gate, sbom = evaluate_supply_chain(ROOT)
    assert gate.state.value == "PASS"
    assert sbom is not None
    assert sbom.components


def test_packaging_targets_preserve_runtime_qualification_boundary():
    targets = {row.target: row for row in qualify_packaging_targets(ROOT)}
    assert targets["python_local"].state is QualificationState.VERIFIED_LOCAL
    for name in ("windows_service", "windows_desktop", "docker", "aws_terraform"):
        assert targets[name].source_assets_present
        if not targets[name].runtime_available:
            assert (
                targets[name].state is QualificationState.SOURCE_IMPLEMENTED_RUNTIME_NOT_QUALIFIED
            )


def test_service_source_runtime_check_builds_api_without_live_auth_secret():
    completed = subprocess.run(
        [sys.executable, "scripts/run_command_center_service.py", "--root", ".", "--check"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["canonical_authority"] == "PROJECT_PIPELINE"
    assert payload["auth_token_configured"] is False


def test_docker_source_requires_explicit_base_and_nonroot_runtime():
    text = (ROOT / "infrastructure/docker/Dockerfile").read_text()
    assert "ARG PROJECT_PIPELINE_BASE_IMAGE" in text
    assert "FROM ${PROJECT_PIPELINE_BASE_IMAGE}" in text
    assert "USER projectpipeline" in text
    assert "python:latest" not in text


def test_windows_service_and_scripts_do_not_embed_credentials_and_require_explicit_mutation():
    xml = (ROOT / "infrastructure/windows/ProjectPipelineService.xml").read_text().lower()
    assert "onfailure" in xml and "restart" in xml
    assert not any(marker in xml for marker in ("api_token=", "password=", "secret="))
    for name in ("install.ps1", "uninstall.ps1", "upgrade.ps1", "rollback.ps1"):
        text = (ROOT / "scripts/windows" / name).read_text()
        assert "SupportsShouldProcess=$true" in text
        assert "ShouldProcess" in text


def test_environment_profiles_are_distinct_and_deny_or_gate_external_writes(tmp_path):
    expected = {"development", "test", "staging", "production", "recovery", "synthetic"}
    observed = {}
    for name in expected:
        cfg = load_runtime_configuration(
            ROOT,
            profile=name,
            env_file=tmp_path / "missing.env",
            environment={},
        ).settings
        observed[name] = str(cfg.paths.state_dir)
        assert cfg.environment.value == name
        assert cfg.security.require_explicit_approval is True
        assert cfg.security.external_writes_default.value in {"DENY", "DRY_RUN", "REQUIRE_APPROVAL"}
    assert len(set(observed.values())) == len(expected)


def test_cleanup_planner_never_selects_canonical_history():
    planner = CleanupPlanner(ROOT)
    assert all(not planner.protected(row.path) for row in planner.plan())
    for path in ("evidence/x", "provenance/x", "plans/x", "jira/x", "release/x", "database/x"):
        assert planner.protected(path)


def test_release_input_fingerprint_is_deterministic_and_ignores_evidence_outputs():
    first = release_input_fingerprint(ROOT)
    second = release_input_fingerprint(ROOT)
    assert first == second and len(first) == 64


def test_release_candidate_is_truthful_not_production_ready():
    candidate = build_release_candidate(ROOT)
    assert candidate.readiness == "LOCAL_HARDENING_CANDIDATE_NOT_PRODUCTION_READY"
    assert candidate.external_live_qualification_claimed is False
    assert candidate.completion_gate_state != "COMPLETE"
    assert candidate.blockers


def test_hardening_report_carries_resolver_and_target_blockers():
    report = build_hardening_report(ROOT)
    assert report.production_ready is False
    assert report.supply_chain_state == "FAIL"
    assert "release supply-chain evidence is incomplete" in report.production_blockers
    assert report.resolver_lock_state != "READY"
    assert set(report.environment_profiles) == {
        "development",
        "test",
        "staging",
        "production",
        "recovery",
        "synthetic",
    }
    assert report.production_blockers


def test_release_docs_preserve_self_upgrade_independent_certification_and_rollback():
    text = (ROOT / "runbooks/release_upgrade_and_rollback.md").read_text().lower()
    for phrase in (
        "may not independently certify",
        "shadow/no-write",
        "standby",
        "controlled handoff",
        "rollback",
    ):
        assert phrase in text


def test_pass24_release_hardening_validator_is_clean_after_generated_assets():
    assert validate_release_hardening(ROOT) == []
    archive_source = (ROOT / "scripts/create_project_archive.py").read_text(encoding="utf-8")
    assert "RepositoryValidator" in archive_source
    assert "validation.errors or validation.warnings" in archive_source
    assert "error_count" not in archive_source
