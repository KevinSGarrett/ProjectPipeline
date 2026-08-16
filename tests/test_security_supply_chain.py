from datetime import UTC, datetime, timedelta

from project_pipeline.domain.security import GateState, SupplyChainFindingKind
from project_pipeline.security.supply_chain import (
    artifact_integrity,
    assess_self_modification,
    build_repository_sbom,
    build_scanner_evidence,
    evaluate_ci_workflows,
    evaluate_supply_chain,
    release_provenance,
)


def test_sbom_is_deterministic(project_root):
    a = build_repository_sbom(project_root)
    b = build_repository_sbom(project_root)
    assert a.sbom_id == b.sbom_id and a.components == b.components and len(a.components) > 0


def test_ci_is_explicit_permissions_and_hardened(project_root):
    findings = evaluate_ci_workflows(project_root)
    assert not [f for f in findings if f.blocking]
    assert not [f for f in findings if "Harden-Runner" in f.message]


def test_supply_chain_gate_passes_local_policy(project_root):
    gate, sbom = evaluate_supply_chain(project_root)
    assert gate.state is GateState.PASS and sbom is not None


def _release_inputs(project_root, *, observed_at_utc: datetime, payload=None):
    manifest_sha256 = build_repository_sbom(project_root).source_manifest_sha256
    evidence = build_scanner_evidence(
        tool="osv-scanner",
        payload={"results": []} if payload is None else payload,
        source_manifest_sha256=manifest_sha256,
        observed_at_utc=observed_at_utc,
        evidence_path="evidence/osv-release.json",
    )
    integrity = artifact_integrity(project_root, "README.md")
    provenance, _ = release_provenance(
        project_root,
        builder_identity_id="IDENT-00000000000000000000",
        evidence_ids=("EVID-RELEASE",),
    )
    return evidence, integrity, provenance


def test_release_gate_fails_closed_without_required_evidence(project_root):
    gate, _ = evaluate_supply_chain(project_root, release_mode=True)
    assert gate.state is GateState.FAIL
    assert {finding.kind.value for finding in gate.findings if finding.blocking} >= {
        "VULNERABILITY",
        "PROVENANCE",
        "INTEGRITY",
    }


def test_release_gate_accepts_fresh_manifest_bound_clean_evidence(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, provenance = _release_inputs(project_root, observed_at_utc=now)
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=(integrity,),
        provenance=provenance,
        now_utc=now,
    )
    assert gate.state is GateState.PASS


def test_release_gate_rejects_stale_or_wrong_manifest_scan_evidence(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    stale, integrity, provenance = _release_inputs(
        project_root, observed_at_utc=now - timedelta(days=2)
    )
    wrong_manifest = stale.model_copy(
        update={
            "source_manifest_sha256": "0" * 64,
            "observed_at_utc": now,
        }
    )
    for evidence in (stale, wrong_manifest):
        gate, _ = evaluate_supply_chain(
            project_root,
            release_mode=True,
            scanner_evidence=(evidence,),
            integrity_records=(integrity,),
            provenance=provenance,
            now_utc=now,
        )
        assert gate.state is GateState.FAIL
        assert any(finding.kind.value == "VULNERABILITY" for finding in gate.findings)


def test_trivy_high_vulnerability_is_normalized_and_blocks_release(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    payload = {
        "Results": [
            {
                "Target": "requirements/environment.lock.json",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-1234",
                        "PkgName": "example-package",
                        "InstalledVersion": "1.0.0",
                        "Severity": "HIGH",
                        "Title": "example high severity vulnerability",
                    }
                ],
            }
        ]
    }
    manifest_sha256 = build_repository_sbom(project_root).source_manifest_sha256
    evidence = build_scanner_evidence(
        tool="trivy",
        payload=payload,
        source_manifest_sha256=manifest_sha256,
        observed_at_utc=now,
        scanned_kinds=(SupplyChainFindingKind.VULNERABILITY,),
    )
    integrity = artifact_integrity(project_root, "README.md")
    provenance, _ = release_provenance(
        project_root,
        builder_identity_id="IDENT-00000000000000000000",
        evidence_ids=("EVID-RELEASE",),
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=(integrity,),
        provenance=provenance,
        now_utc=now,
    )
    assert gate.state is GateState.FAIL
    finding = next(item for item in gate.findings if item.subject == "example-package@1.0.0")
    assert finding.severity.value == "HIGH" and finding.blocking


def test_scanner_evidence_rejects_malformed_payload(project_root):
    manifest_sha256 = build_repository_sbom(project_root).source_manifest_sha256
    try:
        build_scanner_evidence(
            tool="osv-scanner",
            payload={"results": "not-a-list"},
            source_manifest_sha256=manifest_sha256,
            observed_at_utc=datetime.now(UTC),
        )
    except ValueError as error:
        assert "results" in str(error)
    else:
        raise AssertionError("malformed scanner payload must fail closed")


def test_artifact_integrity_matches_file(project_root):
    x = artifact_integrity(project_root, "README.md")
    assert len(x.sha256) == 64 and x.size_bytes > 0


def test_release_provenance_binds_sbom_and_source(project_root):
    p, s = release_provenance(
        project_root, builder_identity_id="IDENT-00000000000000000000", evidence_ids=("EVID-TEST",)
    )
    assert (
        p.source_aggregate_sha256 == s.source_manifest_sha256
        and p.verification_state == "VERIFIED_LOCAL"
    )


def test_self_modification_control_plane_requires_review():
    a = assess_self_modification(("src/project_pipeline/security/policy.py",))
    assert (
        a.touches_control_plane and a.requires_independent_review and a.requires_rollback_material
    )
    b = assess_self_modification(("docs/README.md",))
    assert not b.touches_control_plane
