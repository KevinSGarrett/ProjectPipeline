"""Public-safe provenance and notice-authority coverage."""

from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.security.license_compliance import (
    build_notice_document,
    license_compliance_authority,
    notice_key,
)
from project_pipeline.security.supply_chain import build_repository_sbom

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTICES = REPO_ROOT / "third_party/NOTICES.generated.json"


def test_generated_notices_are_in_sync_with_the_lock() -> None:
    lock = json.loads(
        (REPO_ROOT / "requirements/environment.lock.json").read_text(encoding="utf-8")
    )
    entries = [
        {
            "component_type": "python-package",
            "name": package["name"],
            "version": package["version"],
            "license": lock["licenses"][package["name"]],
            "source": "requirements/environment.lock.json",
            "digest": package.get("metadata_sha256"),
        }
        for package in lock["packages"]
    ]
    expected = build_notice_document(entries=entries, scope="python-runtime-closure")
    actual = json.loads(NOTICES.read_text(encoding="utf-8"))
    assert actual["entries_sha256"] == expected["entries_sha256"]
    assert actual["entries"] == expected["entries"]


def test_notice_document_is_deterministic() -> None:
    document = json.loads(NOTICES.read_text(encoding="utf-8"))
    rebuilt = build_notice_document(entries=list(document["entries"]), scope=document["scope"])
    assert rebuilt["entries_sha256"] == document["entries_sha256"]
    shuffled = list(reversed(document["entries"]))
    assert (
        build_notice_document(entries=shuffled, scope=document["scope"])["entries_sha256"]
        == document["entries_sha256"]
    ), "notice hashing must not depend on input ordering"


def test_every_compliance_provenance_reference_resolves() -> None:
    sbom = build_repository_sbom(REPO_ROOT)
    authority = license_compliance_authority(REPO_ROOT)
    for component in sbom.components:
        if component.compliance is None:
            continue
        notice = authority.resolve_notice(component.compliance.notice_reference)
        assert notice is not None, component.name
        assert notice["license"] == component.license
        assert notice["source"] == component.source
        assert component.compliance.provenance_reference_id.startswith("LPRV-")
        assert component.compliance.permitted_use_record_id.startswith("LPUR-")
        assert component.compliance.modification_obligation_record_id.startswith("LMOR-")


def test_unreferenced_notice_lookup_returns_none() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    assert (
        authority.resolve_notice("third_party/NOTICES.generated.json#python-package:nope@0") is None
    )


def test_modification_obligations_track_license_family() -> None:
    authority = license_compliance_authority(REPO_ROOT)
    assert authority.modification_obligation("Apache-2.0") == "RETAIN_NOTICE_AND_STATE_CHANGES"
    assert authority.modification_obligation("PostgreSQL") == "RETAIN_NOTICE"
    assert authority.modification_obligation("MIT") == "RETAIN_NOTICE_AND_COPYRIGHT"


def test_notice_keys_are_component_specific() -> None:
    assert notice_key("python-package", "a", "1") != notice_key("python-package", "a", "2")
    assert notice_key("python-package", "a", "1") != notice_key("upstream-integration", "a", "1")
