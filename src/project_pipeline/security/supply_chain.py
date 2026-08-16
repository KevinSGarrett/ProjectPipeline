from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path

from project_pipeline.domain.security import (
    ArtifactIntegrityRecord,
    GateState,
    ReleaseProvenance,
    SBOMComponent,
    SoftwareBillOfMaterials,
    SupplyChainFinding,
    SupplyChainFindingKind,
    SupplyChainGateResult,
    SupplyChainSeverity,
    security_identifier,
)

_SHA_ACTION = re.compile(r"^[0-9a-f]{40}$")
_OFFICIAL_MAJOR_TAG_ACTIONS = {
    "actions/checkout",
    "actions/setup-python",
    "actions/upload-artifact",
    "actions/download-artifact",
}


def _manifest_aggregate(root: Path) -> str:
    data = json.loads((root / "PROJECT_MANIFEST.json").read_text(encoding="utf-8"))
    return str(data["aggregate_sha256"])


def build_repository_sbom(
    root: Path, *, project_id: str = "PROJECT-PIPELINE"
) -> SoftwareBillOfMaterials:
    root = root.resolve()
    lock = json.loads((root / "requirements/environment.lock.json").read_text(encoding="utf-8"))
    components: list[SBOMComponent] = []
    for package in sorted(
        lock.get("packages", []), key=lambda item: (item["name"].casefold(), item["version"])
    ):
        components.append(
            SBOMComponent(
                component_id=security_identifier(
                    "SCOMP", "python", package["name"], package["version"]
                ),
                name=package["name"],
                version=package["version"],
                component_type="python-package",
                source="requirements/environment.lock.json",
                metadata_sha256=package.get("metadata_sha256"),
            )
        )
    registry = json.loads((root / "provenance/upstream_registry.json").read_text(encoding="utf-8"))
    usage = {
        json.loads(line)["upstream_id"]: json.loads(line)
        for line in (root / "provenance/upstream_usage.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    implemented_states = {
        "ACTIVE_RUNTIME",
        "OPTIONAL_ADAPTER_IMPLEMENTED",
        "EXTERNAL_CLI_ADAPTER_IMPLEMENTED",
        "ARCHITECTURE_PATTERN_ADOPTED",
        "IMPLEMENTATION_PATTERN_ADOPTED",
        "TEST_PATTERN_ADOPTED",
        "INCORPORATED_ASSET",
    }
    for item in registry.get("entries", []):
        record = usage.get(item["upstream_id"])
        if not record or record.get("usage_state") not in implemented_states:
            continue
        name = f"{item['owner']}/{item['repository']}"
        revision = item.get("inspected_revision", "unknown")
        components.append(
            SBOMComponent(
                component_id=security_identifier(
                    "SCOMP", "upstream", item["upstream_id"], revision
                ),
                name=name,
                version=revision,
                component_type="upstream-integration",
                license=item.get("license"),
                source=item.get("canonical_url"),
            )
        )
    aggregate = _manifest_aggregate(root)
    return SoftwareBillOfMaterials(
        sbom_id=security_identifier("SBOM", project_id, aggregate, str(len(components))),
        project_id=project_id,
        source_manifest_sha256=aggregate,
        components=tuple(components),
    )


def evaluate_ci_workflows(root: Path) -> tuple[SupplyChainFinding, ...]:
    findings: list[SupplyChainFinding] = []
    workflows = root / ".github/workflows"
    if not workflows.exists():
        return ()
    for path in sorted(workflows.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root).as_posix()
        if not re.search(r"(?m)^permissions:\s*$", text):
            findings.append(
                SupplyChainFinding(
                    finding_id=security_identifier("SGATE", rel, "permissions"),
                    kind=SupplyChainFindingKind.CI_PERMISSION,
                    severity=SupplyChainSeverity.HIGH,
                    subject=rel,
                    message="workflow lacks explicit top-level permissions",
                    source_tool="project-pipeline-ci-policy",
                    blocking=True,
                )
            )
        for match in re.finditer(r"(?m)^\s*-\s+uses:\s*([^\s#]+)", text):
            spec = match.group(1).strip()
            if "@" not in spec:
                blocking = True
            else:
                action, ref = spec.rsplit("@", 1)
                blocking = not (
                    _SHA_ACTION.fullmatch(ref)
                    or (action in _OFFICIAL_MAJOR_TAG_ACTIONS and re.fullmatch(r"v\d+", ref))
                )
            if blocking:
                findings.append(
                    SupplyChainFinding(
                        finding_id=security_identifier("SGATE", rel, "action", spec),
                        kind=SupplyChainFindingKind.ACTION_PINNING,
                        severity=SupplyChainSeverity.HIGH,
                        subject=spec,
                        message="third-party action must be pinned to a reviewed immutable SHA; approved official actions may use reviewed major tags",
                        source_tool="project-pipeline-ci-policy",
                        blocking=True,
                    )
                )
        if "step-security/harden-runner@" not in text:
            findings.append(
                SupplyChainFinding(
                    finding_id=security_identifier("SGATE", rel, "harden-runner"),
                    kind=SupplyChainFindingKind.CI_PERMISSION,
                    severity=SupplyChainSeverity.MEDIUM,
                    subject=rel,
                    message="workflow does not include the selected Harden-Runner profile",
                    source_tool="project-pipeline-ci-policy",
                    blocking=False,
                )
            )
    return tuple(findings)


def evaluate_supply_chain(
    root: Path,
    *,
    external_findings: Iterable[SupplyChainFinding] = (),
    require_sbom: bool = True,
) -> tuple[SupplyChainGateResult, SoftwareBillOfMaterials | None]:
    root = root.resolve()
    findings = list(evaluate_ci_workflows(root)) + list(external_findings)
    sbom = build_repository_sbom(root) if require_sbom else None
    if require_sbom and sbom is None:
        findings.append(
            SupplyChainFinding(
                finding_id=security_identifier("SGATE", "sbom", "missing"),
                kind=SupplyChainFindingKind.SBOM,
                severity=SupplyChainSeverity.HIGH,
                subject="repository",
                message="required software bill of materials is unavailable",
                source_tool="project-pipeline-sbom",
                blocking=True,
            )
        )
    state = GateState.FAIL if any(item.blocking for item in findings) else GateState.PASS
    reasons = (
        ("blocking supply-chain findings remain",)
        if state is GateState.FAIL
        else ("required supply-chain policy checks passed",)
    )
    gate = SupplyChainGateResult(
        gate_id=security_identifier(
            "SGATE", _manifest_aggregate(root), str(len(findings)), state.value
        ),
        state=state,
        findings=tuple(findings),
        sbom_id=sbom.sbom_id if sbom else None,
        reasons=reasons,
    )
    return gate, sbom


def artifact_integrity(root: Path, relative_path: str) -> ArtifactIntegrityRecord:
    path = (root / relative_path).resolve()
    path.relative_to(root.resolve())
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return ArtifactIntegrityRecord(
        integrity_id=security_identifier("INTEGRITY", relative_path, digest),
        artifact_path=relative_path,
        sha256=digest,
        size_bytes=len(data),
    )


def release_provenance(
    root: Path,
    *,
    builder_identity_id: str,
    evidence_ids: tuple[str, ...],
    project_id: str = "PROJECT-PIPELINE",
) -> tuple[ReleaseProvenance, SoftwareBillOfMaterials]:
    sbom = build_repository_sbom(root, project_id=project_id)
    sbom_payload = json.dumps(
        sbom.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    sbom_sha = hashlib.sha256(sbom_payload).hexdigest()
    aggregate = _manifest_aggregate(root)
    record = ReleaseProvenance(
        provenance_id=security_identifier(
            "PROV", project_id, aggregate, builder_identity_id, sbom_sha
        ),
        project_id=project_id,
        source_aggregate_sha256=aggregate,
        builder_identity_id=builder_identity_id,
        sbom_sha256=sbom_sha,
        verification_state="VERIFIED_LOCAL" if evidence_ids else "UNVERIFIED",
        evidence_ids=evidence_ids,
    )
    return record, sbom


def assess_self_modification(changed_paths: tuple[str, ...]):
    from project_pipeline.domain.security import SelfModificationAssessment

    sensitive_prefixes = (
        "src/project_pipeline/control/",
        "src/project_pipeline/security/",
        "src/project_pipeline/assurance/",
        "database/migrations/",
        "config/",
        "provenance/",
    )
    touches = any(
        any(path.startswith(prefix) for prefix in sensitive_prefixes) for path in changed_paths
    )
    reasons = (
        (
            "change touches control, security, assurance, migration, configuration, or provenance authority",
        )
        if touches
        else ("change is outside identified control-plane authority paths",)
    )
    return SelfModificationAssessment(
        assessment_id=security_identifier("SELFCHG", *(changed_paths or ("none",))),
        changed_paths=changed_paths,
        touches_control_plane=touches,
        required_review_classes=("SECURITY", "RECOVERY", "ASSURANCE")
        if touches
        else ("AFFECTED_BEHAVIOR",),
        requires_independent_review=touches,
        requires_rollback_material=touches,
        requires_security_verification=touches,
        reasons=reasons,
    )
