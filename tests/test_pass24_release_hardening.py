"""Public-safe release-hardening coverage.

The hardening report is a local pre-release snapshot. It must never declare
itself production ready, and it must keep emitting the self-certification
boundary blocker regardless of how much other evidence exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.release_hardening.hardening import build_hardening_report
from project_pipeline.release_hardening.pre_admission import (
    SELF_CERTIFICATION_BOUNDARY_BLOCKER,
    PreAdmissionState,
    evaluate_pre_admission_release_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_hardening_report_is_never_production_ready() -> None:
    report = build_hardening_report(REPO_ROOT)
    assert report.production_ready is False


def test_hardening_report_always_emits_the_self_certification_boundary() -> None:
    report = build_hardening_report(REPO_ROOT)
    assert SELF_CERTIFICATION_BOUNDARY_BLOCKER in report.production_blockers


def test_hardening_runs_on_a_public_checkout_without_private_content() -> None:
    # The upstream ledger is private control-plane content; its absence must
    # degrade to UNKNOWN rather than raise.
    report = build_hardening_report(REPO_ROOT)
    assert report.packaging_targets
    assert report.supply_chain_state in {"PASS", "FAIL", "WARN"}


def test_pre_admission_does_not_require_the_final_completion_gate() -> None:
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT)
    assert verdict.state is not PreAdmissionState.ERROR
    assert SELF_CERTIFICATION_BOUNDARY_BLOCKER not in verdict.blockers


def test_pre_admission_reports_resolver_state_from_recorded_verification() -> None:
    verdict = evaluate_pre_admission_release_gate(REPO_ROOT)
    policy = json.loads((REPO_ROOT / "config/dependency_policy.json").read_text(encoding="utf-8"))
    assert verdict.resolver_lock_state == policy["resolver_lock"]["state"]


def test_resolver_ready_requires_executable_verification_evidence() -> None:
    policy = json.loads((REPO_ROOT / "config/dependency_policy.json").read_text(encoding="utf-8"))
    resolver = policy["resolver_lock"]
    if resolver["state"] != "READY":
        return
    verification = resolver["verification"]
    assert verification["verification_exit_code"] == 0
    assert verification["clean_install_exit_code"] == 0
    assert len(verification["lock_sha256"]) == 64
    assert len(verification["export_sha256"]) == 64
    assert verification["uv_version"]
    assert verification["verified_on_host"]


def test_stale_blocked_external_cannot_survive_successful_verification() -> None:
    policy = json.loads((REPO_ROOT / "config/dependency_policy.json").read_text(encoding="utf-8"))
    resolver = policy["resolver_lock"]
    verification = resolver.get("verification") or {}
    if verification.get("verification_exit_code") == 0:
        assert resolver["state"] != "BLOCKED_EXTERNAL"
        assert verification.get("supersedes_state") == "BLOCKED_EXTERNAL"


def test_recorded_lock_hashes_match_the_committed_artifacts() -> None:
    import hashlib

    policy = json.loads((REPO_ROOT / "config/dependency_policy.json").read_text(encoding="utf-8"))
    verification = policy["resolver_lock"].get("verification") or {}
    if not verification:
        return
    lock_bytes = (REPO_ROOT / policy["resolver_lock"]["path"]).read_bytes()
    assert hashlib.sha256(lock_bytes).hexdigest() == verification["lock_sha256"]
    export_bytes = (REPO_ROOT / verification["export_path"]).read_bytes()
    assert hashlib.sha256(export_bytes).hexdigest() == verification["export_sha256"]
