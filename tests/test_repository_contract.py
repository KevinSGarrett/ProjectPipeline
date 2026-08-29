"""Public-safe repository contract coverage.

Public production code must not depend on private control-plane content. The
same code must also keep working when a private control plane *is* provisioned.
Set PROJECT_PIPELINE_PRIVATE_ROOT to a provisioned checkout to exercise the
second environment.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from project_pipeline.release_hardening.hardening import build_hardening_report
from project_pipeline.security.license_compliance import license_compliance_authority
from project_pipeline.security.supply_chain import (
    build_repository_sbom,
    evaluate_supply_chain,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

PRIVATE_ONLY_PATHS = (
    "plans",
    "evidence",
    "jira",
    "instructions",
    "dummy",
    "PROJECT_MANIFEST.json",
    "config/project_manifest.json",
)


def _private_root() -> Path | None:
    configured = os.environ.get("PROJECT_PIPELINE_PRIVATE_ROOT")
    if configured:
        candidate = Path(configured)
        if (candidate / "provenance/license_policy.json").is_file():
            return candidate
    if (REPO_ROOT / "provenance/license_policy.json").is_file():
        return REPO_ROOT
    return None


def test_private_control_plane_content_is_not_committed() -> None:
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for path in PRIVATE_ONLY_PATHS:
        offenders = [row for row in tracked if row == path or row.startswith(f"{path}/")]
        assert offenders == [], f"private content must not be tracked: {offenders[:3]}"


def test_public_checkout_builds_an_sbom() -> None:
    sbom = build_repository_sbom(REPO_ROOT)
    assert sbom.components
    assert sbom.source_manifest_sha256


def test_public_checkout_loads_license_policy() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    assert authority.automatic_approval_spdx
    assert authority.prohibited_spdx
    assert authority.rules


def test_public_checkout_evaluates_release_mode_without_private_content() -> None:
    gate, _ = evaluate_supply_chain(REPO_ROOT, release_mode=True)
    assert gate.state.value in {"PASS", "FAIL", "WARN"}


def test_public_checkout_builds_a_hardening_report() -> None:
    report = build_hardening_report(REPO_ROOT)
    assert report.production_ready is False


def test_public_policy_is_available_without_the_private_copy() -> None:
    assert (REPO_ROOT / "config/license_policy.json").is_file()
    policy = json.loads((REPO_ROOT / "config/license_policy.json").read_text(encoding="utf-8"))
    assert policy["automatic_approval_spdx"]


@pytest.mark.skipif(_private_root() is None, reason="no provisioned private control plane")
def test_provisioned_control_plane_still_validates() -> None:
    root = _private_root()
    assert root is not None
    sbom = build_repository_sbom(root)
    assert sbom.components
    # A provisioned root adds upstream integrations beyond the public closure.
    assert any(c.component_type == "upstream-integration" for c in sbom.components)
    gate, _ = evaluate_supply_chain(root, release_mode=True)
    license_findings = [f for f in gate.findings if f.kind.value == "LICENSE"]
    assert license_findings == []
    report = build_hardening_report(root)
    assert report.production_ready is False
