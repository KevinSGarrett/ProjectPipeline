from project_pipeline.domain.security import GateState
from project_pipeline.security.supply_chain import (
    artifact_integrity,
    assess_self_modification,
    build_repository_sbom,
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
