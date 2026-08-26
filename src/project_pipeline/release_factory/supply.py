from __future__ import annotations

import hashlib
import json
import os
import re
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
# Concatenate PEM headers so this module is not itself flagged as residue.
_SECRET_PATTERNS = (
    re.compile("BEGIN OPENSSH PRIVATE " + "KEY"),
    re.compile("BEGIN RSA PRIVATE " + "KEY"),
    re.compile("BEGIN EC PRIVATE " + "KEY"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xoxb-[A-Za-z0-9-]{20,}"),
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
    license_inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    license_inventory_integrity_id: str


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


def _os_path(path: Path) -> Path:
    """Return a filesystem path that can exceed the legacy Windows MAX_PATH limit."""
    if os.name != "nt":
        return path
    raw = os.fspath(path)
    if raw.startswith("\\\\?\\") or raw.startswith("//?/"):
        return path
    text = os.path.abspath(os.fspath(path))
    if text.startswith("\\\\?\\"):
        return Path(text)
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def _mkdir_p(path: Path) -> None:
    os.makedirs(os.fspath(_os_path(path)), exist_ok=True)


def extract_zip_safely(archive: Path, dest: Path) -> tuple[Path, ...]:
    _mkdir_p(dest)
    root = Path(os.path.abspath(os.fspath(dest)))
    written: list[Path] = []
    with zipfile.ZipFile(archive) as payload:
        for info in payload.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or name.endswith("/"):
                continue
            if _zip_member_is_escaped(info.filename, root):
                raise ValueError(f"archive traversal rejected: {info.filename}")
            parts = [part for part in name.split("/") if part not in {"", "."}]
            target = root.joinpath(*parts)
            _mkdir_p(target.parent)
            _os_path(target).write_bytes(payload.read(info))
            written.append(target)
    return tuple(written)


def _scan_secrets(paths: tuple[Path, ...]) -> None:
    for path in paths:
        os_path = _os_path(path)
        if not os_path.is_file():
            continue
        text = os_path.read_bytes()
        try:
            decoded = text.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(decoded) for pattern in _SECRET_PATTERNS):
            raise ValueError(f"secret residue rejected in {path.name}")


def _authenticode_state() -> str:
    return BLOCKED_EXTERNAL_SIGNING_IDENTITY_MISSING


def _materialize_public_license_inventory(
    output_dir: Path,
    *,
    sbom: SoftwareBillOfMaterials,
) -> Path:
    missing = sorted(
        f"{component.name}=={component.version}"
        for component in sbom.components
        if not isinstance(component.license, str) or not component.license.strip()
    )
    if missing:
        raise ValueError(
            "license inventory requires verified license metadata: " + ", ".join(missing)
        )
    payload = {
        "schema_version": "1.0.0",
        "generated_for": "PUBLIC_SOURCE_CHECKOUT",
        "components": [
            {
                "component_id": component.component_id,
                "name": component.name,
                "version": component.version,
                "component_type": component.component_type,
                "license": component.license,
                "source": component.source,
            }
            for component in sbom.components
        ],
    }
    relative_path = Path("provenance") / "license_policy.generated.json"
    path = output_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _resolve_license_inventory_path(
    root: Path, output_dir: Path, *, sbom: SoftwareBillOfMaterials
) -> tuple[str, str, int]:
    license_path = root / "provenance" / "license_policy.json"
    if license_path.is_file():
        relative_path = Path("provenance") / "license_policy.json"
        materialized = output_dir / relative_path
        materialized.parent.mkdir(parents=True, exist_ok=True)
        materialized.write_bytes(license_path.read_bytes())
    elif (root / "provenance").exists():
        raise ValueError("license policy is missing")
    else:
        materialized = _materialize_public_license_inventory(output_dir, sbom=sbom)
        relative_path = materialized.relative_to(output_dir)
    return (
        relative_path.as_posix(),
        hashlib.sha256(materialized.read_bytes()).hexdigest(),
        materialized.stat().st_size,
    )


def _inventory_path(output_dir: Path, relative_path: str) -> Path:
    root = output_dir.resolve()
    candidate = (root / relative_path).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("license inventory path escapes bundle output")
    return candidate


def verify_supply_binding(output_dir: Path, binding: SupplyBinding) -> None:
    """Fail closed when a bound license inventory is absent or altered."""

    inventory_path = _inventory_path(output_dir, binding.license_inventory_path)
    if not inventory_path.is_file():
        raise ValueError("bound license inventory is missing")
    actual_sha256 = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    if actual_sha256 != binding.license_inventory_sha256:
        raise ValueError("bound license inventory digest mismatch")
    provenance_path = output_dir / "provenance.json"
    if not provenance_path.is_file():
        raise ValueError("bound provenance is missing")
    provenance = ReleaseProvenance.model_validate_json(provenance_path.read_text(encoding="utf-8"))
    if (
        binding.license_inventory_path not in provenance.declared_artifact_paths
        or binding.license_inventory_integrity_id not in provenance.artifact_integrity_ids
    ):
        raise ValueError("bound license inventory is absent from provenance")


def bind_bundle_supply_chain(
    root: Path, bundle: ReleaseBundle, *, extract_kind: str = "source_archive"
) -> SupplyBinding:
    root = root.resolve()
    output = Path(bundle.output_dir)
    checksums = {item.name: item.sha256 for item in bundle.artifacts if item.bound}
    sbom = build_repository_sbom(root)
    license_path, license_sha256, license_size = _resolve_license_inventory_path(
        root, output, sbom=sbom
    )
    _scan_secrets((_inventory_path(output, license_path),))
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
    license_integrity = ArtifactIntegrityRecord(
        integrity_id=security_identifier("INTEGRITY", "license-inventory", license_sha256),
        artifact_path=license_path,
        sha256=license_sha256,
        size_bytes=license_size,
        signature_state="NOT_REQUIRED",
    )
    integrity_ids.append(license_integrity.integrity_id)
    provenance = ReleaseProvenance(
        provenance_id=security_identifier("PROV", bundle.cache_key, bundle.version.source_sha),
        project_id="PROJECT-PIPELINE",
        source_aggregate_sha256=bundle.cache_key,
        builder_identity_id="actor:cycle-016-combined",
        sbom_sha256=sbom_sha256,
        verification_state="BOUND_UNSIGNED",
        evidence_ids=("EVID-000216",),
        declared_artifact_paths=(
            *(item.name for item in bundle.artifacts if item.bound),
            license_path,
        ),
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
    binding = SupplyBinding(
        bundle_cache_key=bundle.cache_key,
        sbom_sha256=sbom_sha256,
        provenance_id=provenance.provenance_id,
        checksums=checksums,
        clean_extraction=True,
        secret_scan="CLEAN",
        authenticode_state=_authenticode_state(),
        license_inventory_path=license_path,
        license_inventory_sha256=license_sha256,
        license_inventory_integrity_id=license_integrity.integrity_id,
    )
    verify_supply_binding(output, binding)
    return binding
