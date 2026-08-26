from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from project_pipeline.release_factory.bundle import BoundArtifact, ReleaseBundle
from project_pipeline.release_factory.supply import bind_bundle_supply_chain, verify_supply_binding
from project_pipeline.release_factory.version import ReleaseVersionAuthority


def _write_minimal_lock(root: Path) -> None:
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "requirements" / "environment.lock.json").write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "name": "example-package",
                        "version": "1.2.3",
                        "metadata_sha256": "d" * 64,
                    }
                ],
                "licenses": {"example-package": "MIT"},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_source_archive(path: Path) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as payload:
        payload.writestr("README.md", "fixture source archive\n")
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _fixture_bundle(output_dir: Path) -> ReleaseBundle:
    archive = output_dir / "project-pipeline-source.zip"
    digest, size = _write_source_archive(archive)
    version = ReleaseVersionAuthority(
        bundle_version="0.9.0",
        desktop_version="0.10.0",
        source_sha="a" * 40,
        source_tree="b" * 40,
        sources={
            "pyproject": "0.9.0",
            "platform": "0.9.0",
            "python_package": "0.9.0",
            "command_center_npm": "0.10.0",
            "tauri": "0.10.0",
            "cargo": "0.10.0",
        },
        dual_identity=True,
        tag_name="v0.9.0-rc.aaaaaaaaaaaa",
    )
    artifact = BoundArtifact(
        kind="source_archive",
        name=archive.name,
        sha256=digest,
        size_bytes=size,
        source_sha=version.source_sha,
        source_tree=version.source_tree,
    )
    return ReleaseBundle(
        cache_key="c" * 64,
        version=version,
        artifacts=(artifact,),
        output_dir=str(output_dir),
        desktop_bound=True,
        resumable=False,
    )


def test_bind_bundle_supply_chain_generates_public_license_inventory() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"
        output = Path(directory) / "bundle"
        root.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=True, exist_ok=True)
        _write_minimal_lock(root)
        bundle = _fixture_bundle(output)

        binding = bind_bundle_supply_chain(root, bundle)
        generated = output / binding.license_inventory_path
        provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
        assert generated.name == "license_policy.generated.json"
        assert generated.is_file()
        assert (
            binding.license_inventory_sha256 == hashlib.sha256(generated.read_bytes()).hexdigest()
        )
        assert (
            json.loads(generated.read_text(encoding="utf-8"))["components"][0]["license"] == "MIT"
        )
        assert binding.license_inventory_path in provenance["declared_artifact_paths"]
        assert binding.license_inventory_integrity_id in provenance["artifact_integrity_ids"]
        verify_supply_binding(output, binding)
        generated.write_text("tampered\n", encoding="utf-8")
        with pytest.raises(ValueError, match="bound license inventory digest mismatch"):
            verify_supply_binding(output, binding)


def test_bind_bundle_supply_chain_rejects_partial_provenance_state() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"
        output = Path(directory) / "bundle"
        root.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=True, exist_ok=True)
        _write_minimal_lock(root)
        (root / "provenance").mkdir(parents=True, exist_ok=True)
        bundle = _fixture_bundle(output)

        with pytest.raises(ValueError, match="license policy is missing"):
            bind_bundle_supply_chain(root, bundle)


def test_bind_bundle_supply_chain_rejects_missing_verified_license(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    output = tmp_path / "bundle"
    root.mkdir()
    output.mkdir()
    _write_minimal_lock(root)
    lock_path = root / "requirements" / "environment.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["licenses"] = {}
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    with pytest.raises(ValueError, match="environment lock license is missing"):
        bind_bundle_supply_chain(root, _fixture_bundle(output))
