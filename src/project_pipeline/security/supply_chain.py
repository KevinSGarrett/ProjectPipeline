from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from project_pipeline.domain.security import (
    ArtifactIntegrityRecord,
    GateState,
    ProvenanceEvidenceKind,
    ReleaseProvenance,
    SBOMComponent,
    ScannerEvidence,
    SelfModificationAssessment,
    SoftwareBillOfMaterials,
    SupplyChainFinding,
    SupplyChainFindingKind,
    SupplyChainGateResult,
    SupplyChainSeverity,
    security_fingerprint,
    security_identifier,
)
from project_pipeline.manifest import build_manifest
from project_pipeline.security.license_compliance import (
    license_compliance_authority,
    notice_key,
)

_SHA_ACTION = re.compile(r"^[0-9a-f]{40}$")
_PROVENANCE_EVIDENCE_ID = re.compile(r"^(SCANEVID|INTEGRITY|SIG|EVID)-[A-Z0-9-]{8,}$")
_OFFICIAL_MAJOR_TAG_ACTIONS = {
    "actions/checkout",
    "actions/setup-python",
    "actions/upload-artifact",
    "actions/download-artifact",
}
_DEFAULT_SCANNER_MAX_AGE = timedelta(hours=24)
_DEFAULT_REQUIRED_SCAN_KINDS = (
    SupplyChainFindingKind.VULNERABILITY,
    SupplyChainFindingKind.MISCONFIGURATION,
)
_DEFAULT_REQUIRED_TARGET_CLASSES = (
    "source",
    "dependency",
    "container",
    "infrastructure",
)
_ALLOWED_RELEASE_TARGET_CLASSES = frozenset(_DEFAULT_REQUIRED_TARGET_CLASSES)


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    return value


def _rows(value: object, *, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a list")
    return value


def _severity(value: object, *, default: SupplyChainSeverity) -> SupplyChainSeverity:
    normalized = str(value or "").strip().upper()
    aliases = {"UNKNOWN": default, "MODERATE": SupplyChainSeverity.MEDIUM}
    if normalized in aliases:
        return aliases[normalized]
    try:
        return SupplyChainSeverity(normalized)
    except ValueError:
        return default


def _normalized_finding(
    *,
    tool: str,
    kind: SupplyChainFindingKind,
    severity: SupplyChainSeverity,
    subject: str,
    external_id: str,
    message: str,
    evidence_path: str | None,
) -> SupplyChainFinding:
    return SupplyChainFinding(
        finding_id=security_identifier("SGATE", tool, kind.value, subject, external_id),
        kind=kind,
        severity=severity,
        subject=subject,
        message=message,
        source_tool=tool,
        evidence_path=evidence_path,
        blocking=severity in {SupplyChainSeverity.HIGH, SupplyChainSeverity.CRITICAL},
    )


def _normalize_osv(payload: object, *, evidence_path: str | None) -> tuple[SupplyChainFinding, ...]:
    document = _mapping(payload, context="OSV Scanner result")
    results = _rows(document.get("results"), context="OSV Scanner results")
    findings: list[SupplyChainFinding] = []
    for result_index, result_value in enumerate(results):
        result = _mapping(result_value, context=f"OSV result {result_index}")
        packages = _rows(result.get("packages", []), context=f"OSV result {result_index} packages")
        for package_index, package_value in enumerate(packages):
            package = _mapping(
                package_value,
                context=f"OSV result {result_index} package {package_index}",
            )
            package_data = _mapping(
                package.get("package", {}),
                context=f"OSV result {result_index} package identity",
            )
            name = str(package_data.get("name") or "unknown-package")
            version = str(package_data.get("version") or "unknown-version")
            vulnerabilities = _rows(
                package.get("vulnerabilities", []),
                context=f"OSV result {result_index} vulnerabilities",
            )
            for vulnerability_index, vulnerability_value in enumerate(vulnerabilities):
                vulnerability = _mapping(
                    vulnerability_value,
                    context=(f"OSV result {result_index} vulnerability {vulnerability_index}"),
                )
                database_specific = _mapping(
                    vulnerability.get("database_specific", {}),
                    context="OSV database_specific",
                )
                external_id = str(
                    vulnerability.get("id")
                    or f"unknown-{result_index}-{package_index}-{vulnerability_index}"
                )
                severity = _severity(
                    database_specific.get("severity"),
                    default=SupplyChainSeverity.HIGH,
                )
                findings.append(
                    _normalized_finding(
                        tool="osv-scanner",
                        kind=SupplyChainFindingKind.VULNERABILITY,
                        severity=severity,
                        subject=f"{name}@{version}",
                        external_id=external_id,
                        message=str(
                            vulnerability.get("summary")
                            or vulnerability.get("details")
                            or external_id
                        ),
                        evidence_path=evidence_path,
                    )
                )
    return tuple(findings)


def _normalize_trivy_collection(
    *,
    result: Mapping[str, object],
    result_index: int,
    key: str,
    kind: SupplyChainFindingKind,
    evidence_path: str | None,
) -> tuple[SupplyChainFinding, ...]:
    rows = _rows(result.get(key, []), context=f"Trivy result {result_index} {key}")
    findings: list[SupplyChainFinding] = []
    target = str(result.get("Target") or "repository")
    for row_index, row_value in enumerate(rows):
        row = _mapping(row_value, context=f"Trivy {key} row {row_index}")
        external_id = str(
            row.get("VulnerabilityID")
            or row.get("RuleID")
            or row.get("ID")
            or row.get("Category")
            or f"unknown-{result_index}-{row_index}"
        )
        package = str(row.get("PkgName") or row.get("PackageName") or "")
        version = str(row.get("InstalledVersion") or row.get("Version") or "")
        subject = (
            f"{package}@{version}" if package and version else str(row.get("Target") or target)
        )
        default = (
            SupplyChainSeverity.CRITICAL
            if kind is SupplyChainFindingKind.SECRET
            else SupplyChainSeverity.MEDIUM
        )
        severity = _severity(row.get("Severity"), default=default)
        findings.append(
            _normalized_finding(
                tool="trivy",
                kind=kind,
                severity=severity,
                subject=subject,
                external_id=external_id,
                message=str(
                    row.get("Title") or row.get("Message") or row.get("Description") or external_id
                ),
                evidence_path=evidence_path,
            )
        )
    return tuple(findings)


def _normalize_trivy(
    payload: object, *, evidence_path: str | None
) -> tuple[SupplyChainFinding, ...]:
    document = _mapping(payload, context="Trivy result")
    results = _rows(document.get("Results"), context="Trivy Results")
    findings: list[SupplyChainFinding] = []
    collections = (
        ("Vulnerabilities", SupplyChainFindingKind.VULNERABILITY),
        ("Secrets", SupplyChainFindingKind.SECRET),
        ("Misconfigurations", SupplyChainFindingKind.MISCONFIGURATION),
        ("Licenses", SupplyChainFindingKind.LICENSE),
    )
    for result_index, result_value in enumerate(results):
        result = _mapping(result_value, context=f"Trivy result {result_index}")
        for key, kind in collections:
            findings.extend(
                _normalize_trivy_collection(
                    result=result,
                    result_index=result_index,
                    key=key,
                    kind=kind,
                    evidence_path=evidence_path,
                )
            )
    return tuple(findings)


def _normalize_gitleaks(
    payload: object, *, evidence_path: str | None
) -> tuple[SupplyChainFinding, ...]:
    findings: list[SupplyChainFinding] = []
    for index, value in enumerate(_rows(payload, context="Gitleaks result")):
        row = _mapping(value, context=f"Gitleaks finding {index}")
        subject = str(row.get("File") or "repository")
        external_id = str(row.get("Fingerprint") or row.get("RuleID") or f"finding-{index}")
        findings.append(
            _normalized_finding(
                tool="gitleaks",
                kind=SupplyChainFindingKind.SECRET,
                severity=SupplyChainSeverity.CRITICAL,
                subject=subject,
                external_id=external_id,
                message=str(row.get("Description") or "potential secret detected"),
                evidence_path=evidence_path,
            )
        )
    return tuple(findings)


def build_scanner_evidence(
    *,
    tool: str,
    payload: object,
    source_manifest_sha256: str,
    observed_at_utc: datetime,
    scanned_kinds: tuple[SupplyChainFindingKind, ...] | None = None,
    execution_state: Literal["SUCCEEDED", "FAILED"] = "SUCCEEDED",
    evidence_path: str | None = None,
) -> ScannerEvidence:
    """Normalize supported scanner output and bind it to one source manifest."""

    normalized_tool = tool.strip().casefold()
    inferred_kinds: tuple[SupplyChainFindingKind, ...]
    if normalized_tool in {"osv", "osv-scanner"}:
        canonical_tool = "osv-scanner"
        inferred_kinds = (SupplyChainFindingKind.VULNERABILITY,)
        findings = _normalize_osv(payload, evidence_path=evidence_path)
    elif normalized_tool == "trivy":
        canonical_tool = "trivy"
        if not scanned_kinds:
            raise ValueError("Trivy evidence must identify the configured scanner kinds")
        inferred_kinds = scanned_kinds
        findings = _normalize_trivy(payload, evidence_path=evidence_path)
    elif normalized_tool == "gitleaks":
        canonical_tool = "gitleaks"
        inferred_kinds = (SupplyChainFindingKind.SECRET,)
        findings = _normalize_gitleaks(payload, evidence_path=evidence_path)
    else:
        raise ValueError(f"unsupported scanner evidence tool: {tool}")
    if scanned_kinds is not None and normalized_tool != "trivy" and scanned_kinds != inferred_kinds:
        raise ValueError(f"{canonical_tool} scanner kinds do not match its governed capability")
    result_sha256 = security_fingerprint(payload)
    if observed_at_utc.tzinfo is None or observed_at_utc.utcoffset() is None:
        raise ValueError("scanner observation time must be timezone-aware")
    observed = observed_at_utc.astimezone(UTC)
    return ScannerEvidence(
        scanner_evidence_id=security_identifier(
            "SCANEVID",
            canonical_tool,
            source_manifest_sha256,
            result_sha256,
            observed.isoformat(),
        ),
        tool=canonical_tool,
        execution_state=execution_state,
        source_manifest_sha256=source_manifest_sha256,
        result_sha256=result_sha256,
        observed_at_utc=observed,
        scanned_kinds=inferred_kinds,
        findings=findings,
        evidence_path=evidence_path,
    )


def _manifest_aggregate(root: Path) -> str:
    manifest_path = root / "PROJECT_MANIFEST.json"
    if manifest_path.is_file():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return str(data["aggregate_sha256"])
    # Public-source checkouts may omit persisted manifest files.
    return str(build_manifest(root)["aggregate_sha256"])


def build_repository_sbom(
    root: Path, *, project_id: str = "PROJECT-PIPELINE"
) -> SoftwareBillOfMaterials:
    root = root.resolve()
    lock = json.loads((root / "requirements/environment.lock.json").read_text(encoding="utf-8"))
    licenses = lock.get("licenses")
    if not isinstance(licenses, dict):
        raise ValueError("environment lock license inventory is missing")
    authority = license_compliance_authority(root)
    components: list[SBOMComponent] = []
    for package in sorted(
        lock.get("packages", []), key=lambda item: (item["name"].casefold(), item["version"])
    ):
        license_value = licenses.get(package["name"])
        if not isinstance(license_value, str) or not license_value.strip():
            raise ValueError(f"environment lock license is missing: {package['name']}")
        source = "requirements/environment.lock.json"
        digest = package.get("metadata_sha256")
        components.append(
            SBOMComponent(
                component_id=security_identifier(
                    "SCOMP", "python", package["name"], package["version"]
                ),
                name=package["name"],
                version=package["version"],
                component_type="python-package",
                license=license_value,
                source=source,
                metadata_sha256=digest,
                compliance=authority.compliance_for(
                    name=package["name"],
                    version=package["version"],
                    component_type="python-package",
                    license_expression=license_value,
                    source=source,
                    digest=digest,
                ),
            )
        )
    registry_path = root / "provenance/upstream_registry.json"
    usage_path = root / "provenance/upstream_usage.jsonl"
    registry_exists = registry_path.is_file()
    usage_exists = usage_path.is_file()
    if registry_exists != usage_exists:
        raise ValueError(
            "upstream provenance ledger is incomplete; upstream_registry.json and "
            "upstream_usage.jsonl must be both present or both absent"
        )
    if registry_exists and usage_exists:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        usage = {
            json.loads(line)["upstream_id"]: json.loads(line)
            for line in usage_path.read_text(encoding="utf-8").splitlines()
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
                    compliance=authority.compliance_for(
                        name=name,
                        version=revision,
                        component_type="upstream-integration",
                        license_expression=item.get("license") or "",
                        source=item.get("canonical_url"),
                        digest=item.get("inspected_revision"),
                    ),
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


def _release_requirement_finding(
    *,
    kind: SupplyChainFindingKind,
    subject: str,
    code: str,
    message: str,
    evidence_path: str | None = None,
) -> SupplyChainFinding:
    return SupplyChainFinding(
        finding_id=security_identifier("SGATE", "release", kind.value, subject, code),
        kind=kind,
        severity=SupplyChainSeverity.HIGH,
        subject=subject,
        message=message,
        source_tool="project-pipeline-release-gate",
        evidence_path=evidence_path,
        blocking=True,
    )


def _normalize_release_artifact_path(root: Path, artifact_path: str) -> str:
    normalized = artifact_path.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("release artifact path must be non-empty")
    if normalized.startswith("/"):
        raise ValueError("release artifact path must be relative to repository root")
    resolved = (root / normalized).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("release artifact path escapes repository root") from error
    if not resolved.is_file():
        raise ValueError("release artifact path does not exist as a file")
    return resolved.relative_to(root).as_posix()


def _normalize_target_classes(classes: Iterable[str], *, context: str) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in classes:
        target = str(value).strip().casefold()
        if not target:
            raise ValueError(f"{context} contains an empty target class")
        if target not in _ALLOWED_RELEASE_TARGET_CLASSES:
            raise ValueError(f"{context} contains unsupported target class '{target}'")
        if target not in normalized:
            normalized.append(target)
    if not normalized:
        raise ValueError(f"{context} must contain at least one target class")
    return tuple(normalized)


def _sbom_sha256(sbom: SoftwareBillOfMaterials) -> str:
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


def release_distribution_scope(root: Path) -> frozenset[str]:
    """Return notice keys for components the release actually distributes.

    The environment lock observes every active dependency group, including
    test-only closure members. Only the runtime closure is shipped, so license
    distribution obligations are scoped to it. Upstream integrations are always
    in scope because adopted implementations ship inside the product.
    """

    keys = set()
    lock_path = root / "requirements/environment.lock.json"
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        for package in lock.get("packages", []):
            if "runtime" in (package.get("closure_groups") or []):
                keys.add(notice_key("python-package", package["name"], package["version"]))

    # An upstream integration is only distributed when the release actually
    # carries upstream material: copied source paths, or an incorporated asset.
    # Adapter implementations and independently implemented patterns
    # redistribute nothing, so distribution obligations do not attach.
    registry_path = root / "provenance/upstream_registry.json"
    usage_path = root / "provenance/upstream_usage.jsonl"
    if registry_path.is_file() and usage_path.is_file():
        registry = {
            item["upstream_id"]: item
            for item in json.loads(registry_path.read_text(encoding="utf-8")).get("entries", [])
        }
        for line in usage_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            carries_source = bool(record.get("copied_source_paths")) or (
                record.get("usage_state") == "INCORPORATED_ASSET"
            )
            if not carries_source:
                continue
            item = registry.get(record["upstream_id"])
            if item is None:
                continue
            keys.add(
                notice_key(
                    "upstream-integration",
                    f"{item['owner']}/{item['repository']}",
                    item.get("inspected_revision", "unknown"),
                )
            )
    return frozenset(keys)


def _is_distributed(component: SBOMComponent, distributed: frozenset[str]) -> bool:
    return notice_key(component.component_type, component.name, component.version) in distributed


def _evaluate_license_policy(
    root: Path, components: tuple[SBOMComponent, ...]
) -> tuple[SupplyChainFinding, ...]:
    authority = license_compliance_authority(root)

    prohibited = set(authority.prohibited_spdx)
    review_required = set(authority.review_required_spdx)
    rules = authority.rules
    distributed = release_distribution_scope(root)
    findings: list[SupplyChainFinding] = []
    for component in components:
        license_expression = (component.license or "").strip()
        # Prohibited licenses are rejected everywhere. Every other obligation
        # applies only to what the release actually distributes; development
        # and test-only closure members are not shipped.
        if license_expression not in prohibited and not _is_distributed(component, distributed):
            continue
        if not license_expression:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.LICENSE,
                    subject=component.name,
                    code="license-missing",
                    message=(
                        "third-party component license is missing and cannot be policy-qualified; "
                        "record machine-verifiable notice, permitted use, modification obligations, "
                        "provenance, and bounded source-adaptation requirements"
                    ),
                )
            )
            continue
        if license_expression in prohibited:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.LICENSE,
                    subject=component.name,
                    code="license-prohibited",
                    message=f"license '{license_expression}' is prohibited by policy",
                )
            )
            continue
        if license_expression in review_required:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.LICENSE,
                    subject=component.name,
                    code="license-review-required",
                    message=(
                        f"license '{license_expression}' is not autonomously policy-qualified for activation; "
                        "record machine-verifiable notice, permitted use, modification obligations, "
                        "provenance, and bounded source-adaptation requirements"
                    ),
                )
            )
            continue
        if not authority.is_automatically_approved(license_expression):
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.LICENSE,
                    subject=component.name,
                    code="license-unknown",
                    message=(
                        f"license '{license_expression}' is not in automatic approvals and must be "
                        "treated as review-required with full legal/provenance recording"
                    ),
                )
            )
            continue
        if not component.source:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.LICENSE,
                    subject=component.name,
                    code="license-provenance-missing",
                    message="approved license still requires recorded provenance/source reference",
                )
            )
            continue
        if component.compliance is None:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.LICENSE,
                    subject=component.name,
                    code="license-compliance-missing",
                    message=(
                        "approved license still requires compliance records (notice, permitted use, "
                        "modification obligations, and provenance binding)"
                    ),
                )
            )
            continue
        if not authority.verify(
            component.compliance,
            name=component.name,
            version=component.version,
            component_type=component.component_type,
            license_expression=license_expression,
            source=component.source,
            digest=component.metadata_sha256
            if component.component_type == "python-package"
            else component.version,
        ):
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.LICENSE,
                    subject=component.name,
                    code="license-compliance-unverifiable",
                    message=(
                        "compliance record does not recompute from component identity, policy, "
                        "and notice authority"
                    ),
                )
            )
            continue
        if not rules:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.LICENSE,
                    subject=component.name,
                    code="license-policy-rules-missing",
                    message="license policy rules are missing for compliance obligations",
                )
            )
    return tuple(findings)


def _validate_integrity_records(
    root: Path, records: tuple[ArtifactIntegrityRecord, ...]
) -> tuple[SupplyChainFinding, ...]:
    findings: list[SupplyChainFinding] = []
    for record in records:
        path = (root / record.artifact_path).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            valid = False
        else:
            valid = path.is_file()
        if valid:
            data = path.read_bytes()
            valid = (
                len(data) == record.size_bytes and hashlib.sha256(data).hexdigest() == record.sha256
            )
        if not valid:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.INTEGRITY,
                    subject=record.artifact_path,
                    code="artifact-mismatch",
                    message="artifact content does not match its release integrity record",
                )
            )
    return tuple(findings)


def _validate_release_artifact_coverage(
    root: Path,
    *,
    declared_artifact_paths: tuple[str, ...],
    records: tuple[ArtifactIntegrityRecord, ...],
    signing_required: bool,
) -> tuple[SupplyChainFinding, ...]:
    findings: list[SupplyChainFinding] = []
    normalized_declared: list[str] = []
    for artifact_path in declared_artifact_paths:
        try:
            normalized_declared.append(_normalize_release_artifact_path(root, artifact_path))
        except ValueError as error:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.INTEGRITY,
                    subject=artifact_path,
                    code="declared-artifact-invalid",
                    message=f"declared release artifact is invalid: {error}",
                )
            )
    if not normalized_declared:
        findings.append(
            _release_requirement_finding(
                kind=SupplyChainFindingKind.INTEGRITY,
                subject="release candidate",
                code="declared-artifact-set-missing",
                message="release evaluation requires a declared release-artifact set",
            )
        )
        return tuple(findings)
    declared_set = set(normalized_declared)
    for artifact in sorted(declared_set):
        if normalized_declared.count(artifact) > 1:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.INTEGRITY,
                    subject=artifact,
                    code="declared-artifact-duplicate",
                    message="declared release-artifact set contains duplicates",
                )
            )
    records_by_path: dict[str, list[ArtifactIntegrityRecord]] = {}
    for record in records:
        try:
            normalized = _normalize_release_artifact_path(root, record.artifact_path)
        except ValueError as error:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.INTEGRITY,
                    subject=record.artifact_path,
                    code="integrity-record-invalid-path",
                    message=f"integrity record path is invalid: {error}",
                )
            )
            continue
        records_by_path.setdefault(normalized, []).append(record)
    for artifact in sorted(declared_set):
        bound_records = records_by_path.get(artifact, [])
        if not bound_records:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.INTEGRITY,
                    subject=artifact,
                    code="integrity-record-missing",
                    message="declared release artifact has no integrity record",
                )
            )
            continue
        if len(bound_records) > 1:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.INTEGRITY,
                    subject=artifact,
                    code="integrity-record-duplicate",
                    message="declared release artifact has duplicate integrity records",
                )
            )
    for artifact in sorted(records_by_path):
        if artifact not in declared_set:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.INTEGRITY,
                    subject=artifact,
                    code="integrity-record-extra",
                    message="integrity record references a non-declared release artifact",
                )
            )
    single_records = tuple(
        records_by_path[artifact][0]
        for artifact in sorted(declared_set)
        if len(records_by_path.get(artifact, [])) == 1
    )
    findings.extend(_validate_integrity_records(root, single_records))
    if signing_required:
        for artifact in sorted(declared_set):
            bound_records = records_by_path.get(artifact, [])
            if len(bound_records) != 1 or bound_records[0].signature_state != "VERIFIED":
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.SIGNATURE,
                        subject=artifact,
                        code="required-signature-missing",
                        message="declared release artifact lacks a verified signature",
                    )
                )
    return tuple(findings)


def _validate_provenance_evidence_bindings(
    *,
    aggregate: str,
    provenance: ReleaseProvenance,
    scanner_evidence: tuple[ScannerEvidence, ...],
    integrity_records: tuple[ArtifactIntegrityRecord, ...],
    now: datetime,
    scanner_max_age: timedelta,
) -> tuple[SupplyChainFinding, ...]:
    findings: list[SupplyChainFinding] = []
    binding_by_id = {binding.evidence_id: binding for binding in provenance.evidence_bindings}
    for evidence_id in provenance.evidence_ids:
        if not _PROVENANCE_EVIDENCE_ID.fullmatch(evidence_id):
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.PROVENANCE,
                    subject=evidence_id,
                    code="provenance-evidence-id-invalid",
                    message="provenance evidence id is not a governed typed identity",
                )
            )
    if not provenance.evidence_bindings:
        findings.append(
            _release_requirement_finding(
                kind=SupplyChainFindingKind.PROVENANCE,
                subject=provenance.provenance_id,
                code="provenance-evidence-bindings-missing",
                message="verified provenance must include typed evidence bindings",
            )
        )
        return tuple(findings)
    for evidence in scanner_evidence:
        binding = binding_by_id.get(evidence.scanner_evidence_id)
        if binding is None:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.PROVENANCE,
                    subject=evidence.tool,
                    code="scanner-evidence-unbound",
                    message="scanner evidence is not bound by release provenance",
                    evidence_path=evidence.evidence_path,
                )
            )
            continue
        if binding.evidence_kind is not ProvenanceEvidenceKind.SCANNER:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.PROVENANCE,
                    subject=evidence.tool,
                    code="scanner-evidence-kind-mismatch",
                    message="scanner evidence binding kind is invalid",
                    evidence_path=evidence.evidence_path,
                )
            )
        if (
            binding.source_manifest_sha256 != aggregate
            or binding.result_sha256 != evidence.result_sha256
            or binding.tool.casefold() != evidence.tool.casefold()
        ):
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.PROVENANCE,
                    subject=evidence.tool,
                    code="scanner-evidence-binding-mismatch",
                    message="scanner evidence binding does not match evaluated scanner evidence",
                    evidence_path=evidence.evidence_path,
                )
            )
        age = now - binding.observed_at_utc
        if age < -timedelta(minutes=5) or age > scanner_max_age:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.PROVENANCE,
                    subject=evidence.tool,
                    code="scanner-evidence-binding-stale",
                    message="scanner evidence binding timestamp is stale or in the future",
                    evidence_path=evidence.evidence_path,
                )
            )
    for record in integrity_records:
        binding = binding_by_id.get(record.integrity_id)
        if binding is None:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.PROVENANCE,
                    subject=record.artifact_path,
                    code="integrity-evidence-unbound",
                    message="integrity evidence is not bound by release provenance",
                )
            )
            continue
        if binding.evidence_kind is not ProvenanceEvidenceKind.INTEGRITY:
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.PROVENANCE,
                    subject=record.artifact_path,
                    code="integrity-evidence-kind-mismatch",
                    message="integrity evidence binding kind is invalid",
                )
            )
        if (
            binding.source_manifest_sha256 != aggregate
            or binding.result_sha256 != record.sha256
            or binding.tool.casefold() != "integrity"
        ):
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.PROVENANCE,
                    subject=record.artifact_path,
                    code="integrity-evidence-binding-mismatch",
                    message="integrity evidence binding does not match evaluated artifact integrity",
                )
            )
    return tuple(findings)


def evaluate_supply_chain(
    root: Path,
    *,
    external_findings: Iterable[SupplyChainFinding] = (),
    require_sbom: bool = True,
    release_mode: bool = False,
    scanner_evidence: Iterable[ScannerEvidence] = (),
    integrity_records: Iterable[ArtifactIntegrityRecord] = (),
    provenance: ReleaseProvenance | None = None,
    now_utc: datetime | None = None,
    scanner_max_age: timedelta = _DEFAULT_SCANNER_MAX_AGE,
    signing_profile_enabled: bool = False,
    release_artifact_paths: tuple[str, ...] = (),
    scanner_target_coverage: Mapping[str, tuple[str, ...]] | None = None,
    required_scan_kinds: tuple[SupplyChainFindingKind, ...] = _DEFAULT_REQUIRED_SCAN_KINDS,
    required_target_classes: tuple[str, ...] = _DEFAULT_REQUIRED_TARGET_CLASSES,
    sbom_override: SoftwareBillOfMaterials | None = None,
    enforce_license_gate: bool = False,
) -> tuple[SupplyChainGateResult, SoftwareBillOfMaterials | None]:
    root = root.resolve()
    aggregate = _manifest_aggregate(root)
    policy = json.loads((root / "config/security_policy.json").read_text(encoding="utf-8"))
    supply_policy = _mapping(policy.get("supply_chain", {}), context="supply-chain policy")
    effective_require_sbom = require_sbom or (
        release_mode and bool(supply_policy.get("require_sbom"))
    )
    findings = list(evaluate_ci_workflows(root)) + list(external_findings)
    records = tuple(integrity_records)
    sbom = (
        (sbom_override if sbom_override is not None else build_repository_sbom(root))
        if effective_require_sbom
        else None
    )
    if effective_require_sbom and sbom is None:
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
    if sbom is not None and sbom.source_manifest_sha256 != aggregate:
        findings.append(
            _release_requirement_finding(
                kind=SupplyChainFindingKind.SBOM,
                subject="release candidate",
                code="sbom-manifest-mismatch",
                message="SBOM is not bound to the current source manifest",
            )
        )
    effective_license_gate = enforce_license_gate or release_mode
    if sbom is not None and effective_license_gate:
        for component in sbom.components:
            if (
                not component.name.strip()
                or not component.version.strip()
                or not component.component_type.strip()
            ):
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.SBOM,
                        subject=component.component_id,
                        code="sbom-component-malformed",
                        message="SBOM component metadata is malformed or incomplete",
                    )
                )
            if component.component_type in {"python-package", "upstream-integration"} and (
                not component.source or not component.source.strip()
            ):
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.SBOM,
                        subject=component.component_id,
                        code="sbom-component-unbound",
                        message="third-party SBOM component lacks required provenance/source binding",
                    )
                )
    if release_mode:
        now = now_utc or datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("release supply-chain evaluation time must be timezone-aware")
        now = now.astimezone(UTC)
        if scanner_max_age <= timedelta(0):
            raise ValueError("scanner evidence maximum age must be positive")
        required_kinds = frozenset(required_scan_kinds)
        if not required_kinds:
            raise ValueError("required release scan kinds must be non-empty")
        required_targets = frozenset(
            _normalize_target_classes(
                required_target_classes, context="required release target classes"
            )
        )
        scanner_coverage = scanner_target_coverage or {}
        qualifying_release_scope_scan = False
        for evidence in tuple(scanner_evidence):
            findings.extend(evidence.findings)
            evidence_valid = True
            if evidence.execution_state != "SUCCEEDED":
                evidence_valid = False
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.INTEGRITY,
                        subject=evidence.tool,
                        code="execution-failed",
                        message="scanner execution did not succeed",
                        evidence_path=evidence.evidence_path,
                    )
                )
            if evidence.source_manifest_sha256 != aggregate:
                evidence_valid = False
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.PROVENANCE,
                        subject=evidence.tool,
                        code="manifest-mismatch",
                        message="scanner evidence is not bound to the current source manifest",
                        evidence_path=evidence.evidence_path,
                    )
                )
            age = now - evidence.observed_at_utc
            if age < -timedelta(minutes=5) or age > scanner_max_age:
                evidence_valid = False
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.PROVENANCE,
                        subject=evidence.tool,
                        code="stale-or-future",
                        message="scanner evidence is stale or has an invalid future timestamp",
                        evidence_path=evidence.evidence_path,
                    )
                )
            scanned_kinds = frozenset(evidence.scanned_kinds)
            missing_kinds = sorted(kind.value for kind in required_kinds - scanned_kinds)
            if missing_kinds:
                evidence_valid = False
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.MISCONFIGURATION,
                        subject=evidence.tool,
                        code="missing-scan-kind-coverage",
                        message=(
                            "release scan evidence is missing required configured scan kinds: "
                            + ", ".join(missing_kinds)
                        ),
                        evidence_path=evidence.evidence_path,
                    )
                )
            coverage_raw = scanner_coverage.get(evidence.scanner_evidence_id, ())
            try:
                covered_targets = frozenset(
                    _normalize_target_classes(
                        coverage_raw,
                        context=f"scanner target coverage for {evidence.scanner_evidence_id}",
                    )
                )
            except ValueError as error:
                evidence_valid = False
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.MISCONFIGURATION,
                        subject=evidence.tool,
                        code="invalid-target-coverage",
                        message=str(error),
                        evidence_path=evidence.evidence_path,
                    )
                )
                covered_targets = frozenset()
            missing_targets = sorted(required_targets - covered_targets)
            if missing_targets:
                evidence_valid = False
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.MISCONFIGURATION,
                        subject=evidence.tool,
                        code="missing-target-coverage",
                        message=(
                            "release scan evidence does not prove coverage for required target classes: "
                            + ", ".join(missing_targets)
                        ),
                        evidence_path=evidence.evidence_path,
                    )
                )
            if evidence_valid:
                qualifying_release_scope_scan = True
        if (
            bool(supply_policy.get("require_vulnerability_scan_for_release"))
            and not qualifying_release_scope_scan
        ):
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.MISCONFIGURATION,
                    subject="release candidate",
                    code="required-scan-missing",
                    message=(
                        "release requires fresh successful scan evidence bound to the current source "
                        "manifest with required vulnerability/misconfiguration kinds and full target "
                        "class coverage"
                    ),
                )
            )
        if bool(supply_policy.get("require_provenance")):
            expected_sbom_sha = _sbom_sha256(sbom) if sbom is not None else None
            provenance_valid = bool(
                provenance is not None
                and provenance.source_aggregate_sha256 == aggregate
                and (expected_sbom_sha is None or provenance.sbom_sha256 == expected_sbom_sha)
                and provenance.verification_state.startswith("VERIFIED")
                and provenance.evidence_ids
            )
            if not provenance_valid:
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.PROVENANCE,
                        subject="release candidate",
                        code="required-provenance-missing",
                        message=(
                            "verified release provenance bound to source, SBOM state, and evidence "
                            "is required"
                        ),
                    )
                )
            else:
                assert provenance is not None
                normalized_declared = tuple(
                    sorted(
                        _normalize_release_artifact_path(root, item)
                        for item in release_artifact_paths
                    )
                )
                provenance_declared = tuple(
                    sorted(
                        _normalize_release_artifact_path(root, item)
                        for item in provenance.declared_artifact_paths
                    )
                )
                if normalized_declared != provenance_declared:
                    findings.append(
                        _release_requirement_finding(
                            kind=SupplyChainFindingKind.PROVENANCE,
                            subject="release candidate",
                            code="provenance-artifact-set-mismatch",
                            message=(
                                "provenance artifact binding does not match the declared release "
                                "artifact set"
                            ),
                        )
                    )
                integrity_ids = tuple(sorted(record.integrity_id for record in records))
                if tuple(sorted(provenance.artifact_integrity_ids)) != integrity_ids:
                    findings.append(
                        _release_requirement_finding(
                            kind=SupplyChainFindingKind.PROVENANCE,
                            subject="release candidate",
                            code="provenance-integrity-set-mismatch",
                            message=(
                                "provenance integrity binding does not match evaluated integrity "
                                "records"
                            ),
                        )
                    )
                findings.extend(
                    _validate_provenance_evidence_bindings(
                        aggregate=aggregate,
                        provenance=provenance,
                        scanner_evidence=tuple(scanner_evidence),
                        integrity_records=records,
                        now=now,
                        scanner_max_age=scanner_max_age,
                    )
                )
        if bool(supply_policy.get("require_integrity_hashes")):
            if records:
                findings.extend(
                    _validate_release_artifact_coverage(
                        root,
                        declared_artifact_paths=release_artifact_paths,
                        records=records,
                        signing_required=(
                            signing_profile_enabled
                            and bool(
                                supply_policy.get(
                                    "require_signed_release_when_signing_profile_enabled"
                                )
                            )
                        ),
                    )
                )
                if provenance is not None:
                    mismatched = [
                        record.artifact_path
                        for record in records
                        if record.provenance_id != provenance.provenance_id
                    ]
                    if mismatched:
                        findings.append(
                            _release_requirement_finding(
                                kind=SupplyChainFindingKind.PROVENANCE,
                                subject=", ".join(sorted(mismatched)),
                                code="integrity-provenance-id-mismatch",
                                message=(
                                    "artifact integrity records must bind the evaluated release "
                                    "provenance id"
                                ),
                            )
                        )
            else:
                findings.append(
                    _release_requirement_finding(
                        kind=SupplyChainFindingKind.INTEGRITY,
                        subject="release candidate",
                        code="required-integrity-missing",
                        message="release artifact integrity records are required",
                    )
                )
        if (
            signing_profile_enabled
            and bool(supply_policy.get("require_signed_release_when_signing_profile_enabled"))
            and not records
        ):
            findings.append(
                _release_requirement_finding(
                    kind=SupplyChainFindingKind.SIGNATURE,
                    subject="release candidate",
                    code="required-signature-missing",
                    message="the enabled signing profile requires verified artifact signatures",
                )
            )
        if effective_license_gate and sbom is not None:
            findings.extend(_evaluate_license_policy(root, sbom.components))
    state = GateState.FAIL if any(item.blocking for item in findings) else GateState.PASS
    if state is GateState.FAIL:
        reason = (
            "release supply-chain evidence is incomplete or blocking findings remain"
            if release_mode
            else "blocking supply-chain findings remain"
        )
    else:
        reason = (
            "required release supply-chain policy checks passed"
            if release_mode
            else "required supply-chain policy checks passed"
        )
    decision_fingerprint = security_fingerprint(
        {
            "aggregate": aggregate,
            "release_mode": release_mode,
            "state": state.value,
            "enforce_license_gate": effective_license_gate,
            "sbom_sha256": _sbom_sha256(sbom) if sbom is not None else None,
            "scanner_evidence": [
                {
                    "scanner_evidence_id": evidence.scanner_evidence_id,
                    "tool": evidence.tool,
                    "execution_state": evidence.execution_state,
                    "source_manifest_sha256": evidence.source_manifest_sha256,
                    "result_sha256": evidence.result_sha256,
                    "observed_at_utc": evidence.observed_at_utc.isoformat(),
                    "scanned_kinds": [item.value for item in evidence.scanned_kinds],
                    "target_coverage": sorted(
                        scanner_target_coverage.get(evidence.scanner_evidence_id, ())
                        if scanner_target_coverage
                        else ()
                    ),
                }
                for evidence in sorted(
                    tuple(scanner_evidence), key=lambda item: item.scanner_evidence_id
                )
            ],
            "integrity_records": [
                {
                    "integrity_id": record.integrity_id,
                    "artifact_path": record.artifact_path,
                    "sha256": record.sha256,
                    "size_bytes": record.size_bytes,
                    "signature_state": record.signature_state,
                }
                for record in sorted(records, key=lambda item: item.integrity_id)
            ],
            "release_artifact_paths": sorted(release_artifact_paths),
            "provenance": (
                {
                    "provenance_id": provenance.provenance_id,
                    "source_aggregate_sha256": provenance.source_aggregate_sha256,
                    "builder_identity_id": provenance.builder_identity_id,
                    "sbom_sha256": provenance.sbom_sha256,
                    "verification_state": provenance.verification_state,
                    "evidence_ids": sorted(provenance.evidence_ids),
                }
                if provenance is not None
                else None
            ),
            "finding_ids": sorted(item.finding_id for item in findings),
            "finding_fingerprint": security_fingerprint(
                [
                    {
                        "finding_id": item.finding_id,
                        "kind": item.kind.value,
                        "severity": item.severity.value,
                        "subject": item.subject,
                        "message": item.message,
                        "blocking": item.blocking,
                    }
                    for item in sorted(findings, key=lambda finding: finding.finding_id)
                ]
            ),
        }
    )
    gate = SupplyChainGateResult(
        gate_id=security_identifier(
            "SGATE",
            aggregate,
            "release" if release_mode else "internal",
            decision_fingerprint,
        ),
        state=state,
        findings=tuple(findings),
        sbom_id=sbom.sbom_id if sbom else None,
        integrity_ids=tuple(record.integrity_id for record in records),
        reasons=(reason,),
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
    sbom_sha = _sbom_sha256(sbom)
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


def assess_self_modification(changed_paths: tuple[str, ...]) -> SelfModificationAssessment:
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
