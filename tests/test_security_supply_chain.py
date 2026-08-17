import hashlib
import json
from datetime import UTC, datetime, timedelta

from project_pipeline.domain.security import (
    GateState,
    ProvenanceEvidenceBinding,
    ProvenanceEvidenceKind,
    ReleaseProvenance,
    SBOMComponent,
    SBOMComponentCompliance,
    SoftwareBillOfMaterials,
    SupplyChainFindingKind,
    security_identifier,
)
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
    artifact_paths = (
        "release/release_candidate_r24.json",
        "release/hardening_report_r24.json",
        "release/sbom_r24.json",
    )
    evidence = build_scanner_evidence(
        tool="trivy",
        payload={"Results": []} if payload is None else payload,
        source_manifest_sha256=manifest_sha256,
        observed_at_utc=observed_at_utc,
        scanned_kinds=(
            SupplyChainFindingKind.VULNERABILITY,
            SupplyChainFindingKind.MISCONFIGURATION,
        ),
        evidence_path="evidence/trivy-release.json",
    )
    integrity = tuple(artifact_integrity(project_root, path) for path in artifact_paths)
    provenance, _ = release_provenance(
        project_root,
        builder_identity_id="IDENT-00000000000000000000",
        evidence_ids=(evidence.scanner_evidence_id, *(row.integrity_id for row in integrity)),
    )
    integrity = tuple(
        row.model_copy(update={"provenance_id": provenance.provenance_id}) for row in integrity
    )
    provenance = provenance.model_copy(
        update={
            "declared_artifact_paths": artifact_paths,
            "artifact_integrity_ids": tuple(row.integrity_id for row in integrity),
            "evidence_bindings": (
                ProvenanceEvidenceBinding(
                    evidence_id=evidence.scanner_evidence_id,
                    evidence_kind=ProvenanceEvidenceKind.SCANNER,
                    source_manifest_sha256=evidence.source_manifest_sha256,
                    result_sha256=evidence.result_sha256,
                    tool=evidence.tool,
                    observed_at_utc=evidence.observed_at_utc,
                ),
                *(
                    ProvenanceEvidenceBinding(
                        evidence_id=row.integrity_id,
                        evidence_kind=ProvenanceEvidenceKind.INTEGRITY,
                        source_manifest_sha256=manifest_sha256,
                        result_sha256=row.sha256,
                        tool="integrity",
                        observed_at_utc=observed_at_utc,
                    )
                    for row in integrity
                ),
            ),
        }
    )
    coverage = {
        evidence.scanner_evidence_id: ("source", "dependency", "container", "infrastructure"),
    }
    return evidence, integrity, provenance, artifact_paths, coverage


def test_release_gate_fails_closed_without_required_evidence(project_root):
    gate, _ = evaluate_supply_chain(project_root, release_mode=True)
    assert gate.state is GateState.FAIL
    assert {finding.kind.value for finding in gate.findings if finding.blocking} >= {
        "MISCONFIGURATION",
        "PROVENANCE",
        "INTEGRITY",
    }


def test_release_gate_accepts_fresh_manifest_bound_clean_evidence(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, provenance, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    sbom = _license_gate_sbom(project_root, license_expression="MIT")
    provenance = provenance.model_copy(update={"sbom_sha256": _sbom_sha(sbom)})
    integrity = tuple(
        row.model_copy(update={"provenance_id": provenance.provenance_id}) for row in integrity
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
        sbom_override=sbom,
    )
    assert gate.state is GateState.PASS


def test_release_gate_rejects_vulnerability_only_evidence_scope(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    manifest_sha256 = build_repository_sbom(project_root).source_manifest_sha256
    evidence = build_scanner_evidence(
        tool="osv-scanner",
        payload={"results": []},
        source_manifest_sha256=manifest_sha256,
        observed_at_utc=now,
        evidence_path="evidence/osv-release.json",
    )
    _, integrity, provenance, artifact_paths, _ = _release_inputs(project_root, observed_at_utc=now)
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage={
            evidence.scanner_evidence_id: ("source", "dependency", "container", "infrastructure")
        },
    )
    assert gate.state is GateState.FAIL
    assert any("scan kinds" in finding.message.lower() for finding in gate.findings)


def test_release_gate_rejects_unrelated_integrity_artifact(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, _, provenance, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    unrelated_integrity = (artifact_integrity(project_root, "README.md"),)
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=unrelated_integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
    )
    assert gate.state is GateState.FAIL
    assert any(
        finding.kind.value == "INTEGRITY" and "release artifact" in finding.message.lower()
        for finding in gate.findings
    )


def test_release_gate_rejects_unrelated_verified_signature(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, _, provenance, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    signed_unrelated = artifact_integrity(project_root, "README.md").model_copy(
        update={"signature_state": "VERIFIED"}
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=(signed_unrelated,),
        provenance=provenance,
        now_utc=now,
        signing_profile_enabled=True,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
    )
    assert gate.state is GateState.FAIL
    assert any(finding.kind.value == "SIGNATURE" for finding in gate.findings)


def test_release_gate_identity_changes_when_findings_change(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    manifest_sha256 = build_repository_sbom(project_root).source_manifest_sha256
    evidence_a = build_scanner_evidence(
        tool="trivy",
        payload={"Results": []},
        source_manifest_sha256=manifest_sha256,
        observed_at_utc=now,
        scanned_kinds=(
            SupplyChainFindingKind.VULNERABILITY,
            SupplyChainFindingKind.MISCONFIGURATION,
        ),
    )
    evidence_b = build_scanner_evidence(
        tool="trivy",
        payload={"Results": [{"Target": "src/project_pipeline/security/supply_chain.py"}]},
        source_manifest_sha256=manifest_sha256,
        observed_at_utc=now,
        scanned_kinds=(
            SupplyChainFindingKind.VULNERABILITY,
            SupplyChainFindingKind.MISCONFIGURATION,
        ),
    )
    artifacts = (
        "release/release_candidate_r24.json",
        "release/hardening_report_r24.json",
        "release/sbom_r24.json",
    )
    integrity = tuple(artifact_integrity(project_root, path) for path in artifacts)
    provenance, _ = release_provenance(
        project_root,
        builder_identity_id="IDENT-00000000000000000000",
        evidence_ids=("EVID-RELEASE",),
    )
    coverage = {
        evidence_a.scanner_evidence_id: ("source", "dependency", "container", "infrastructure"),
        evidence_b.scanner_evidence_id: ("source", "dependency", "container", "infrastructure"),
    }
    gate_a, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence_a,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifacts,
        scanner_target_coverage=coverage,
    )
    gate_b, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence_b,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifacts,
        scanner_target_coverage=coverage,
    )
    assert gate_a.gate_id != gate_b.gate_id


def test_release_gate_rejects_stale_or_wrong_manifest_scan_evidence(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    stale, integrity, provenance, artifact_paths, coverage = _release_inputs(
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
            integrity_records=integrity,
            provenance=provenance,
            now_utc=now,
            release_artifact_paths=artifact_paths,
            scanner_target_coverage={
                evidence.scanner_evidence_id: coverage[stale.scanner_evidence_id]
            },
        )
        assert gate.state is GateState.FAIL
        assert any(finding.kind.value == "PROVENANCE" for finding in gate.findings)


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
    artifacts = (
        "release/release_candidate_r24.json",
        "release/hardening_report_r24.json",
        "release/sbom_r24.json",
    )
    integrity = tuple(artifact_integrity(project_root, path) for path in artifacts)
    provenance, _ = release_provenance(
        project_root,
        builder_identity_id="IDENT-00000000000000000000",
        evidence_ids=("EVID-RELEASE",),
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifacts,
        scanner_target_coverage={
            evidence.scanner_evidence_id: ("source", "dependency", "container", "infrastructure")
        },
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


def _license_gate_sbom(
    project_root, *, license_expression: str | None, include_compliance: bool = True
) -> SoftwareBillOfMaterials:
    source_manifest_sha256 = build_repository_sbom(project_root).source_manifest_sha256
    component = SBOMComponent(
        component_id=security_identifier("SCOMP", "third-party", "example-lib", "1.2.3"),
        name="example-lib",
        version="1.2.3",
        component_type="python-package",
        license=license_expression,
        source="https://example.invalid/example-lib",
        compliance=(
            SBOMComponentCompliance(
                notice_reference="NOTICE/example-lib",
                permitted_use_record_id="PERMITTED-EXAMPLE-LIB",
                modification_obligation_record_id="MOD-EXAMPLE-LIB",
                provenance_reference_id="PROV-EXAMPLE-LIB",
            )
            if include_compliance
            else None
        ),
    )
    return SoftwareBillOfMaterials(
        sbom_id=security_identifier("SBOM", "PROJECT-PIPELINE", source_manifest_sha256, "1"),
        project_id="PROJECT-PIPELINE",
        source_manifest_sha256=source_manifest_sha256,
        components=(component,),
    )


def _license_gate_provenance(sbom: SoftwareBillOfMaterials) -> ReleaseProvenance:
    return ReleaseProvenance(
        provenance_id=security_identifier("PROV", "PROJECT-PIPELINE", sbom.sbom_id),
        project_id="PROJECT-PIPELINE",
        source_aggregate_sha256=sbom.source_manifest_sha256,
        builder_identity_id="IDENT-00000000000000000000",
        sbom_sha256="0" * 64,  # overwritten by callers when needed
        verification_state="VERIFIED_LOCAL",
        evidence_ids=("SCANEVID-00000000000000000000",),
    )


def _sbom_sha(sbom: SoftwareBillOfMaterials) -> str:
    payload = json.dumps(
        {
            "project_id": sbom.project_id,
            "source_manifest_sha256": sbom.source_manifest_sha256,
            "components": [
                {
                    "component_id": component.component_id,
                    "name": component.name,
                    "version": component.version,
                    "component_type": component.component_type,
                    "license": component.license,
                    "source": component.source,
                    "metadata_sha256": component.metadata_sha256,
                    "compliance": (
                        {
                            "notice_reference": component.compliance.notice_reference,
                            "permitted_use_record_id": component.compliance.permitted_use_record_id,
                            "modification_obligation_record_id": component.compliance.modification_obligation_record_id,
                            "provenance_reference_id": component.compliance.provenance_reference_id,
                        }
                        if component.compliance is not None
                        else None
                    ),
                }
                for component in sbom.components
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bind_release_provenance(
    *,
    provenance: ReleaseProvenance,
    evidence,
    integrity,
    artifact_paths,
    now: datetime,
) -> ReleaseProvenance:
    return provenance.model_copy(
        update={
            "evidence_ids": (
                evidence.scanner_evidence_id,
                *(row.integrity_id for row in integrity),
            ),
            "declared_artifact_paths": artifact_paths,
            "artifact_integrity_ids": tuple(row.integrity_id for row in integrity),
            "required_signature_state": "NOT_REQUIRED",
            "evidence_bindings": (
                ProvenanceEvidenceBinding(
                    evidence_id=evidence.scanner_evidence_id,
                    evidence_kind=ProvenanceEvidenceKind.SCANNER,
                    source_manifest_sha256=evidence.source_manifest_sha256,
                    result_sha256=evidence.result_sha256,
                    tool=evidence.tool,
                    observed_at_utc=evidence.observed_at_utc,
                ),
                *(
                    ProvenanceEvidenceBinding(
                        evidence_id=row.integrity_id,
                        evidence_kind=ProvenanceEvidenceKind.INTEGRITY,
                        source_manifest_sha256=provenance.source_aggregate_sha256,
                        result_sha256=row.sha256,
                        tool="integrity",
                        observed_at_utc=now,
                    )
                    for row in integrity
                ),
            ),
        }
    )


def test_release_license_gate_allows_auto_approved_spdx(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, _, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    sbom = _license_gate_sbom(project_root, license_expression="MIT")
    provenance = _bind_release_provenance(
        provenance=_license_gate_provenance(sbom).model_copy(
            update={"sbom_sha256": _sbom_sha(sbom)}
        ),
        evidence=evidence,
        integrity=integrity,
        artifact_paths=artifact_paths,
        now=now,
    )
    integrity = tuple(
        row.model_copy(update={"provenance_id": provenance.provenance_id}) for row in integrity
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
        sbom_override=sbom,
        enforce_license_gate=True,
    )
    assert gate.state is GateState.PASS


def test_release_license_gate_blocks_prohibited_spdx(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, _, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    sbom = _license_gate_sbom(project_root, license_expression="AGPL-3.0-only")
    provenance = _bind_release_provenance(
        provenance=_license_gate_provenance(sbom).model_copy(
            update={"sbom_sha256": _sbom_sha(sbom)}
        ),
        evidence=evidence,
        integrity=integrity,
        artifact_paths=artifact_paths,
        now=now,
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
        sbom_override=sbom,
        enforce_license_gate=True,
    )
    assert gate.state is GateState.FAIL
    assert any(finding.kind.value == "LICENSE" for finding in gate.findings)


def test_release_license_gate_blocks_review_required_or_missing_spdx(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, _, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    for license_expression in ("NOASSERTION", None):
        sbom = _license_gate_sbom(project_root, license_expression=license_expression)
        provenance = _bind_release_provenance(
            provenance=_license_gate_provenance(sbom).model_copy(
                update={"sbom_sha256": _sbom_sha(sbom)}
            ),
            evidence=evidence,
            integrity=integrity,
            artifact_paths=artifact_paths,
            now=now,
        )
        gate, _ = evaluate_supply_chain(
            project_root,
            release_mode=True,
            scanner_evidence=(evidence,),
            integrity_records=integrity,
            provenance=provenance,
            now_utc=now,
            release_artifact_paths=artifact_paths,
            scanner_target_coverage=coverage,
            sbom_override=sbom,
            enforce_license_gate=True,
        )
        assert gate.state is GateState.FAIL
        assert any(finding.kind.value == "LICENSE" for finding in gate.findings)


def test_release_provenance_requires_matching_sbom_binding(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, _, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    sbom = _license_gate_sbom(project_root, license_expression="MIT")
    provenance = _bind_release_provenance(
        provenance=_license_gate_provenance(sbom),
        evidence=evidence,
        integrity=integrity,
        artifact_paths=artifact_paths,
        now=now,
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
        sbom_override=sbom,
        enforce_license_gate=True,
    )
    assert gate.state is GateState.FAIL
    assert any(finding.kind.value == "PROVENANCE" for finding in gate.findings)


def test_release_mode_fails_closed_for_prohibited_license_without_opt_in(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, _, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    sbom = _license_gate_sbom(project_root, license_expression="AGPL-3.0-only")
    provenance = _bind_release_provenance(
        provenance=_license_gate_provenance(sbom).model_copy(
            update={"sbom_sha256": _sbom_sha(sbom)}
        ),
        evidence=evidence,
        integrity=integrity,
        artifact_paths=artifact_paths,
        now=now,
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
        sbom_override=sbom,
    )
    assert gate.state is GateState.FAIL
    assert any(item.kind.value == "LICENSE" for item in gate.findings)


def test_release_mode_does_not_accept_arbitrary_provenance_evidence_id(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, _, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    sbom = _license_gate_sbom(project_root, license_expression="MIT")
    provenance = _bind_release_provenance(
        provenance=_license_gate_provenance(sbom).model_copy(
            update={"sbom_sha256": _sbom_sha(sbom), "evidence_ids": ("NOT-A-REAL-EVIDENCE-ID",)}
        ),
        evidence=evidence,
        integrity=integrity,
        artifact_paths=artifact_paths,
        now=now,
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
        sbom_override=sbom,
        enforce_license_gate=True,
    )
    assert gate.state is GateState.FAIL
    assert any(item.kind.value == "PROVENANCE" for item in gate.findings)


def test_release_mode_rejects_provenance_reuse_for_different_artifact_set(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, provenance, _artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=(
            "release/release_candidate_r24.json",
            "release/sbom_r24.json",
        ),
        scanner_target_coverage=coverage,
    )
    assert gate.state is GateState.FAIL
    assert any(item.kind.value == "PROVENANCE" for item in gate.findings)


def test_release_mode_rejects_integrity_records_with_unrelated_provenance_id(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, provenance, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    mismatched_integrity = tuple(
        row.model_copy(update={"provenance_id": "PROV-FFFFFFFFFFFFFFFFFFFF"}) for row in integrity
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=mismatched_integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
    )
    assert gate.state is GateState.FAIL
    assert any(item.kind.value == "PROVENANCE" for item in gate.findings)


def test_auto_approved_license_still_requires_component_compliance_records(project_root):
    now = datetime(2026, 8, 16, 18, tzinfo=UTC)
    evidence, integrity, _, artifact_paths, coverage = _release_inputs(
        project_root, observed_at_utc=now
    )
    sbom = _license_gate_sbom(project_root, license_expression="MIT", include_compliance=False)
    provenance = _bind_release_provenance(
        provenance=_license_gate_provenance(sbom).model_copy(
            update={"sbom_sha256": _sbom_sha(sbom)}
        ),
        evidence=evidence,
        integrity=integrity,
        artifact_paths=artifact_paths,
        now=now,
    )
    gate, _ = evaluate_supply_chain(
        project_root,
        release_mode=True,
        scanner_evidence=(evidence,),
        integrity_records=integrity,
        provenance=provenance,
        now_utc=now,
        release_artifact_paths=artifact_paths,
        scanner_target_coverage=coverage,
        sbom_override=sbom,
        enforce_license_gate=True,
    )
    assert gate.state is GateState.FAIL
    assert any(item.kind.value == "LICENSE" for item in gate.findings)
