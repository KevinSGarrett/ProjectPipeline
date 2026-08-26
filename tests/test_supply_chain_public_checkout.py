from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from project_pipeline.manifest import build_manifest
from project_pipeline.security.supply_chain import build_repository_sbom


def _write_minimal_sbom_inputs(root: Path, *, include_manifest: bool = True) -> None:
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
    if include_manifest:
        (root / "PROJECT_MANIFEST.json").write_text(
            json.dumps({"aggregate_sha256": "a" * 64}) + "\n",
            encoding="utf-8",
        )


def test_build_repository_sbom_allows_public_checkout_without_upstream_registry() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_minimal_sbom_inputs(root)
        sbom = build_repository_sbom(root)

    assert sbom.source_manifest_sha256 == "a" * 64
    assert [item.component_type for item in sbom.components] == ["python-package"]
    assert [item.name for item in sbom.components] == ["example-package"]


def test_build_repository_sbom_includes_upstream_components_when_ledgers_present() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_minimal_sbom_inputs(root)
        (root / "provenance").mkdir(parents=True, exist_ok=True)
        (root / "provenance" / "upstream_registry.json").write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "upstream_id": "UPSTREAM-001",
                            "owner": "example",
                            "repository": "repo",
                            "canonical_url": "https://example.invalid/repo",
                            "inspected_revision": "rev-1",
                            "license": "MIT",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "provenance" / "upstream_usage.jsonl").write_text(
            json.dumps(
                {"upstream_id": "UPSTREAM-001", "usage_state": "ACTIVE_RUNTIME"},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        sbom = build_repository_sbom(root)

    assert sorted(item.component_type for item in sbom.components) == [
        "python-package",
        "upstream-integration",
    ]


def test_build_repository_sbom_rejects_partial_upstream_ledger_state() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_minimal_sbom_inputs(root)
        (root / "provenance").mkdir(parents=True, exist_ok=True)
        (root / "provenance" / "upstream_registry.json").write_text(
            json.dumps({"entries": []}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="upstream provenance ledger is incomplete"):
            build_repository_sbom(root)


def test_build_repository_sbom_falls_back_to_in_memory_manifest_aggregate() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_minimal_sbom_inputs(root, include_manifest=False)
        expected = str(build_manifest(root)["aggregate_sha256"])
        sbom = build_repository_sbom(root)

    assert sbom.source_manifest_sha256 == expected


def test_build_repository_sbom_rejects_missing_license_inventory() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_minimal_sbom_inputs(root)
        lock_path = root / "requirements" / "environment.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock.pop("licenses")
        lock_path.write_text(json.dumps(lock), encoding="utf-8")

        with pytest.raises(ValueError, match="environment lock license inventory is missing"):
            build_repository_sbom(root)
