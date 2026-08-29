"""Public-safe regression coverage for release admission.

These tests pin the boundary between a local pre-release hardening snapshot,
which must never certify itself, and the deterministic Completion Gate that
authorizes publication.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.domain.security import SBOMComponentCompliance
from project_pipeline.release_hardening.hardening import build_hardening_report
from project_pipeline.release_hardening.pre_admission import (
    PreAdmissionState,
    evaluate_pre_admission_release_gate,
)
from project_pipeline.security.supply_chain import (
    build_repository_sbom,
    evaluate_supply_chain,
    license_compliance_authority,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _findings(root: Path) -> tuple[str, ...]:
    gate, _ = evaluate_supply_chain(root, release_mode=True)
    return tuple(finding.message for finding in gate.findings)


def test_every_automatically_approved_component_has_compliance() -> None:
    sbom = build_repository_sbom(REPO_ROOT)
    authority = license_compliance_authority(REPO_ROOT)
    approved = [
        component
        for component in sbom.components
        if (component.license or "") in authority.automatic_approval_spdx
    ]
    assert approved, "expected at least one automatically approved component"
    missing = [component.name for component in approved if component.compliance is None]
    assert missing == [], f"approved components without compliance: {missing}"


def test_release_mode_reports_no_compliance_gap_for_approved_components() -> None:
    messages = _findings(REPO_ROOT)
    compliance_gaps = [text for text in messages if "requires compliance records" in text]
    assert compliance_gaps == []


def test_compliance_records_are_deterministic() -> None:
    first = build_repository_sbom(REPO_ROOT)
    second = build_repository_sbom(REPO_ROOT)
    assert [component.compliance for component in first.components] == [
        component.compliance for component in second.components
    ]


def test_compliance_changes_when_component_identity_changes(tmp_path: Path) -> None:
    sbom = build_repository_sbom(REPO_ROOT)
    approved = next(c for c in sbom.components if c.compliance is not None)
    authority = license_compliance_authority(REPO_ROOT)
    rebound = authority.compliance_for(
        name=approved.name,
        version=approved.version,
        component_type=approved.component_type,
        license_expression=approved.license or "",
        source=approved.source,
        digest="f" * 64,
    )
    assert rebound is not None
    assert rebound.provenance_reference_id != approved.compliance.provenance_reference_id
    assert rebound.permitted_use_record_id != approved.compliance.permitted_use_record_id

    # An unknown version has no notice authority, so it must not be approved.
    assert (
        authority.compliance_for(
            name=approved.name,
            version=approved.version + ".9999",
            component_type=approved.component_type,
            license_expression=approved.license or "",
            source=approved.source,
            digest=approved.metadata_sha256,
        )
        is None
    )


def test_review_required_and_prohibited_licenses_still_fail_closed() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    for expression in ("MPL-2.0", "AGPL-3.0-only", "NOASSERTION", "TOTALLY-UNKNOWN"):
        assert (
            authority.compliance_for(
                name="example",
                version="1.0.0",
                component_type="python-package",
                license_expression=expression,
                source="requirements/environment.lock.json",
                digest="0" * 64,
            )
            is None
        ), f"{expression} must not receive an automatic compliance record"


def test_compliance_requires_resolvable_provenance() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    assert (
        authority.compliance_for(
            name="example",
            version="1.0.0",
            component_type="python-package",
            license_expression="MIT",
            source=None,
            digest=None,
        )
        is None
    )


def test_notice_reference_resolves_to_a_real_record() -> None:
    sbom = build_repository_sbom(REPO_ROOT)
    authority = license_compliance_authority(REPO_ROOT)
    for component in sbom.components:
        if component.compliance is None:
            continue
        assert authority.resolve_notice(component.compliance.notice_reference) is not None


def test_tampered_compliance_is_rejected() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    sbom = build_repository_sbom(REPO_ROOT)
    component = next(c for c in sbom.components if c.compliance is not None)
    identity = {
        "name": component.name,
        "version": component.version,
        "component_type": component.component_type,
        "license_expression": component.license or "",
        "source": component.source,
        "digest": component.metadata_sha256,
    }
    assert authority.verify(component.compliance, **identity)

    tampered = SBOMComponentCompliance(
        notice_reference=component.compliance.notice_reference,
        permitted_use_record_id="LPUR-FABRICATED",
        modification_obligation_record_id=component.compliance.modification_obligation_record_id,
        provenance_reference_id=component.compliance.provenance_reference_id,
    )
    assert not authority.verify(tampered, **identity)


def test_pre_admission_may_pass_while_completion_gate_is_incomplete() -> None:
    report = build_hardening_report(REPO_ROOT)
    assert report.production_ready is False
    assert any("Completion Gate" in blocker for blocker in report.production_blockers)

    gate = evaluate_pre_admission_release_gate(REPO_ROOT)
    assert gate.state is not PreAdmissionState.ERROR
    assert not any("Completion Gate" in blocker for blocker in gate.blockers), (
        "pre-admission must not require the final Completion Gate to be COMPLETE"
    )


def test_release_candidate_cannot_self_certify() -> None:
    report = build_hardening_report(REPO_ROOT)
    assert report.production_ready is False


def test_publication_remains_blocked_before_duration_evidence() -> None:
    from project_pipeline.release_hardening.pre_admission import (
        evaluate_final_publication_gate,
    )

    verdict = evaluate_final_publication_gate(
        REPO_ROOT,
        duration_evidence={},
        completion_gate_complete=False,
        published_bytes_verified=False,
    )
    assert verdict.eligible is False
    assert verdict.blockers


def test_publication_requires_independent_completion_gate() -> None:
    from project_pipeline.release_hardening.pre_admission import (
        evaluate_final_publication_gate,
    )

    verdict = evaluate_final_publication_gate(
        REPO_ROOT,
        duration_evidence={
            "UNATTENDED_4_HOUR": True,
            "UNATTENDED_24_HOUR": True,
            "UNATTENDED_72_HOUR": True,
        },
        completion_gate_complete=False,
        published_bytes_verified=True,
    )
    assert verdict.eligible is False


def test_resolver_ready_requires_recorded_verification() -> None:
    policy = json.loads((REPO_ROOT / "config/dependency_policy.json").read_text(encoding="utf-8"))
    resolver = policy.get("resolver_lock", {})
    if resolver.get("state") == "READY":
        assert resolver.get("verification"), "READY requires recorded verification evidence"
        assert resolver["verification"].get("lock_sha256")
        assert resolver["verification"].get("uv_version")


def test_public_checkout_validates_without_private_control_plane() -> None:
    assert not (REPO_ROOT / "plans").exists() or (REPO_ROOT / "plans").is_dir()
    sbom = build_repository_sbom(REPO_ROOT)
    assert sbom.components
    authority = license_compliance_authority(REPO_ROOT)
    assert authority.automatic_approval_spdx


def test_public_checkout_has_no_unresolved_license_findings() -> None:
    gate, _ = evaluate_supply_chain(REPO_ROOT, release_mode=True)
    assert [f.message for f in gate.findings if f.kind.value == "LICENSE"] == []
