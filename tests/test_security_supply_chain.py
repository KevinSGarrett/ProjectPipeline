"""Public-safe supply-chain and license-compliance coverage."""

from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.security.license_compliance import (
    license_compliance_authority,
    notice_key,
)
from project_pipeline.security.supply_chain import (
    build_repository_sbom,
    evaluate_supply_chain,
    release_distribution_scope,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_no_license_findings_remain_in_release_mode() -> None:
    gate, _ = evaluate_supply_chain(REPO_ROOT, release_mode=True)
    license_findings = [finding for finding in gate.findings if finding.kind.value == "LICENSE"]
    assert license_findings == []


def test_every_distributed_component_has_verifiable_compliance() -> None:
    sbom = build_repository_sbom(REPO_ROOT)
    authority = license_compliance_authority(REPO_ROOT)
    distributed = release_distribution_scope(REPO_ROOT)
    checked = 0
    for component in sbom.components:
        if component.component_type != "python-package":
            continue
        if (
            notice_key(component.component_type, component.name, component.version)
            not in distributed
        ):
            continue
        checked += 1
        assert component.compliance is not None, component.name
        assert authority.verify(
            component.compliance,
            name=component.name,
            version=component.version,
            component_type=component.component_type,
            license_expression=component.license or "",
            source=component.source,
            digest=component.metadata_sha256,
        )
    assert checked > 0


def test_prohibited_licenses_are_rejected_in_every_group() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    for expression in sorted(authority.prohibited_spdx):
        assert not authority.is_automatically_approved(expression)
        assert (
            authority.compliance_for(
                name="prohibited-example",
                version="1.0.0",
                component_type="python-package",
                license_expression=expression,
                source="requirements/environment.lock.json",
                digest="0" * 64,
            )
            is None
        )


def test_conjunctions_are_not_widened() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    assert not authority.is_automatically_approved("Apache-2.0 AND BSD-2-Clause")
    assert not authority.is_automatically_approved("MIT AND MPL-2.0")


def test_disjunction_requires_every_alternative_approved() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    assert authority.is_automatically_approved("Apache-2.0 OR BSD-2-Clause")
    assert not authority.is_automatically_approved("MIT OR AGPL-3.0-only")


def test_distribution_scope_excludes_test_only_components() -> None:
    lock = json.loads(
        (REPO_ROOT / "requirements/environment.lock.json").read_text(encoding="utf-8")
    )
    distributed = release_distribution_scope(REPO_ROOT)
    for package in lock["packages"]:
        key = notice_key("python-package", package["name"], package["version"])
        expected = "runtime" in (package.get("closure_groups") or [])
        assert (key in distributed) is expected, package["name"]


def test_scope_exclusions_are_backed_by_recorded_evidence() -> None:
    evidence = json.loads(
        (REPO_ROOT / "config/license_policy_evidence.json").read_text(encoding="utf-8")
    )
    lock = json.loads(
        (REPO_ROOT / "requirements/environment.lock.json").read_text(encoding="utf-8")
    )
    groups = {p["name"]: p.get("closure_groups") or [] for p in lock["packages"]}
    exclusions = evidence["distribution_scope_exclusions"]
    assert exclusions
    for row in exclusions:
        assert row["decision"] == "OUT_OF_RELEASE_DISTRIBUTION_SCOPE"
        assert row["evidence"]
        # The claim must match the lock rather than the receipt's own wording.
        assert "runtime" not in groups[row["name"]]


def test_tier_one_approval_additions_carry_license_text_evidence() -> None:
    policy = json.loads((REPO_ROOT / "config/license_policy.json").read_text(encoding="utf-8"))
    evidence = json.loads(
        (REPO_ROOT / "config/license_policy_evidence.json").read_text(encoding="utf-8")
    )
    documented = {row["spdx_id"] for row in evidence["automatic_approval_additions"]}
    for row in evidence["automatic_approval_additions"]:
        assert row["tier"] == "TIER_I_POLICY_CHANGE"
        assert row["license_text_authority"]["sha256"]
        assert row["license_text_authority"]["bytes"] > 0
        assert row["metadata_authority"]["field"] == "License-Expression"
        assert row["spdx_id"] in policy["automatic_approval_spdx"]
    assert "PSF-2.0" in documented
