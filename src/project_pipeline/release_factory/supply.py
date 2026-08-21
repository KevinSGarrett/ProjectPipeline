from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Literal

from pydantic import Field

from project_pipeline.contracts.envelopes import ContractModel
from project_pipeline.domain.security import (
    ArtifactIntegrityRecord,
    ReleaseProvenance,
    SBOMComponent,
    SoftwareBillOfMaterials,
    security_identifier,
)
from project_pipeline.release_factory.bundle import ReleaseBundle
from project_pipeline.security.supply_chain import build_repository_sbom

BLOCKED_EXTERNAL_SIGNING_IDENTITY_MISSING = "BLOCKED_EXTERNAL_SIGNING_IDENTITY_MISSING"
_SECRET_MARKERS = (
    "BEGIN OPENSSH PRIVATE " + "KEY",
    "BEGIN RSA PRIVATE " + "KEY",
    "BEGIN EC PRIVATE " + "KEY",
    "github_pat_",
    "ghp_",
    "xoxb-",
)


class SupplyBinding(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    bundle_cache_key: str
    sbom_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance_id: str
    checksums: dict[str, str]
    clean_extraction: bool
    secret_scan: Literal["CLEAN", "FAILED"]
    authenticode_state: str
    license_inventory_path: str


def _zip_member_is_escaped(name: str, root: Path) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        return True
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return True
    try:
        target = root.joinpath(*parts).resolve()
        return target == root or not target.is_relative_to(root)
    except (OSError, ValueError):
        return True


def extract_zip_safely(archive: Path, dest: Path) -> tuple[Path, ...]:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    written: list[Path] = []
    with zipfile.ZipFile(archive) as payload:
        for info in payload.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or name.endswith("/"):
                continue
            if _zip_member_is_escaped(info.filename, root):
                raise ValueError(f"archive traversal rejected: {info.filename}")
            parts = [part for part in name.split("/") if part not in {"", "."}]
            target = root.joinpath(*parts).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload.read(info))
            written.append(target)
    return tuple(written)


def _scan_secrets(paths: tuple[Path, ...]) -> None:
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_bytes()
        try:
            decoded = text.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for marker in _SECRET_MARKERS:
            if marker in decoded:
                raise ValueError(f"secret residue rejected in {path.name}")


def _authenticode_state() -> str:
    return BLOCKED_EXTERNAL_SIGNING_IDENTITY_MISSING


def bind_bundle_supply_chain(
    root: Path, bundle: ReleaseBundle, *, extract_kind: str = "source_archive"
) -> SupplyBinding:
    root = root.resolve()
    output = Path(bundle.output_dir)
    checksums = {item.name: item.sha256 for item in bundle.artifacts if item.bound}
    sbom = build_repository_sbom(root)
    artifact_components = [
        SBOMComponent(
            component_id=security_identifier("SCOMP", "artifact", item.kind, item.sha256),
            name=item.name,
            version=bundle.version.bundle_version,
            component_type=item.kind,
            source=item.name,
            metadata_sha256=item.sha256,
        )
        for item in bundle.artifacts
        if item.bound
    ]
    bound_sbom = SoftwareBillOfMaterials(
        sbom_id=security_identifier("SBOM", bundle.cache_key, str(len(artifact_components))),
        project_id="PROJECT-PIPELINE",
        source_manifest_sha256=sbom.source_manifest_sha256,
        components=sbom.components + tuple(artifact_components),
    )
    sbom_path = output / "sbom.json"
    sbom_path.write_text(
        json.dumps(bound_sbom.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sbom_sha256 = hashlib.sha256(sbom_path.read_bytes()).hexdigest()
    integrity_ids: list[str] = []
    for item in bundle.artifacts:
        if not item.bound:
            continue
        record = ArtifactIntegrityRecord(
            integrity_id=security_identifier("INTEGRITY", item.kind, item.sha256),
            artifact_path=item.name,
            sha256=item.sha256,
            size_bytes=item.size_bytes,
            signature_state="UNVERIFIED",
        )
        integrity_ids.append(record.integrity_id)
    provenance = ReleaseProvenance(
        provenance_id=security_identifier("PROV", bundle.cache_key, bundle.version.source_sha),
        project_id="PROJECT-PIPELINE",
        source_aggregate_sha256=bundle.cache_key,
        builder_identity_id="actor:cycle-016-combined",
        sbom_sha256=sbom_sha256,
        verification_state="BOUND_UNSIGNED",
        evidence_ids=("EVID-000216",),
        declared_artifact_paths=tuple(item.name for item in bundle.artifacts if item.bound),
        artifact_integrity_ids=tuple(integrity_ids),
        required_signature_state="NOT_REQUIRED",
    )
    (output / "provenance.json").write_text(
        json.dumps(provenance.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    archive = next(item for item in bundle.artifacts if item.kind == extract_kind and item.bound)
    extracted = extract_zip_safely(output / archive.name, output / "clean-extract")
    _scan_secrets(extracted)
    license_path = "provenance/license_policy.json"
    if not (root / license_path).is_file():
        raise ValueError("license policy is missing")
    return SupplyBinding(
        bundle_cache_key=bundle.cache_key,
        sbom_sha256=sbom_sha256,
        provenance_id=provenance.provenance_id,
        checksums=checksums,
        clean_extraction=True,
        secret_scan="CLEAN",
        authenticode_state=_authenticode_state(),
        license_inventory_path=license_path,
    )
