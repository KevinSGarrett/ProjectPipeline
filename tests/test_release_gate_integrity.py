"""Integrity coverage for the release-admission authority itself.

Independent review identified three ways the authority could be satisfied
without real evidence: notice hashing that ignored entry bodies, a Tier-I
approval that policy could declare without evidence, and a distribution scope
narrower than what the release actually installs. These tests pin each fix.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from project_pipeline.security.license_compliance import (
    BASELINE_AUTOMATIC_APPROVAL_SPDX,
    license_compliance_authority,
    notice_key,
)
from project_pipeline.security.supply_chain import (
    build_repository_sbom,
    release_distribution_scope,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

LOCK_PATH = "requirements/environment.lock.json"
NOTICES_PATH = "third_party/NOTICES.generated.json"
POLICY_PATH = "config/license_policy.json"
EVIDENCE_PATH = "config/license_policy_evidence.json"
LICENSE_TEXT_PATH = "third_party/licenses/PSF-2.0/typing_extensions-4.16.0-LICENSE.txt"


@pytest.fixture
def mirrored_root(tmp_path: Path) -> Path:
    """Copy just the authority inputs so they can be tampered with safely."""

    for relative in (LOCK_PATH, NOTICES_PATH, POLICY_PATH, EVIDENCE_PATH, LICENSE_TEXT_PATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, target)
    return tmp_path


def _read(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _write(root: Path, relative: str, payload: dict) -> None:
    (root / relative).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_notice_hash_covers_entry_bodies_not_only_keys(mirrored_root: Path) -> None:
    baseline = license_compliance_authority(mirrored_root).notices_sha256

    document = _read(mirrored_root, NOTICES_PATH)
    document["entries"][0]["digest"] = "f" * 64
    _write(mirrored_root, NOTICES_PATH, document)

    tampered = license_compliance_authority(mirrored_root).notices_sha256
    assert tampered != baseline, "editing notice metadata must change the notice authority hash"


def test_compliance_is_withdrawn_when_the_notice_digest_diverges(mirrored_root: Path) -> None:
    """A notice must describe the same artifact the SBOM evaluated."""

    sbom = build_repository_sbom(REPO_ROOT)
    component = next(
        c
        for c in sbom.components
        if c.compliance is not None and c.component_type == "python-package"
    )
    identity = {
        "name": component.name,
        "version": component.version,
        "component_type": component.component_type,
        "license_expression": component.license or "",
        "source": component.source,
        "digest": component.metadata_sha256,
    }
    assert license_compliance_authority(mirrored_root).compliance_for(**identity) is not None

    document = _read(mirrored_root, NOTICES_PATH)
    key = notice_key(component.component_type, component.name, component.version)
    for entry in document["entries"]:
        if notice_key(entry["component_type"], entry["name"], entry["version"]) == key:
            entry["digest"] = "0" * 64
    _write(mirrored_root, NOTICES_PATH, document)

    assert license_compliance_authority(mirrored_root).compliance_for(**identity) is None


def test_tier_one_approval_requires_evidence_at_runtime(mirrored_root: Path) -> None:
    """Policy declaring an approval is not enough; evidence must back it."""

    authority = license_compliance_authority(mirrored_root)
    assert authority.is_automatically_approved("PSF-2.0")

    evidence = _read(mirrored_root, EVIDENCE_PATH)
    evidence["automatic_approval_additions"] = []
    _write(mirrored_root, EVIDENCE_PATH, evidence)

    stripped = license_compliance_authority(mirrored_root)
    assert not stripped.is_automatically_approved("PSF-2.0")
    assert "PSF-2.0" not in stripped.automatic_approval_spdx


def test_undeclared_approval_addition_is_not_honoured(mirrored_root: Path) -> None:
    policy = _read(mirrored_root, POLICY_PATH)
    policy["automatic_approval_spdx"] = sorted(
        {*policy["automatic_approval_spdx"], "AGPL-3.0-only"}
    )
    _write(mirrored_root, POLICY_PATH, policy)

    authority = license_compliance_authority(mirrored_root)
    assert not authority.is_automatically_approved("AGPL-3.0-only")


def test_tier_one_evidence_missing_required_fields_is_rejected(mirrored_root: Path) -> None:
    evidence = _read(mirrored_root, EVIDENCE_PATH)
    for record in evidence["automatic_approval_additions"]:
        record["license_text_authority"] = {"path": "LICENSE"}
    _write(mirrored_root, EVIDENCE_PATH, evidence)

    authority = license_compliance_authority(mirrored_root)
    assert not authority.is_automatically_approved("PSF-2.0")


def test_tier_one_evidence_must_name_a_committed_license_text(mirrored_root: Path) -> None:
    """A digest describing a file outside the repository proves nothing."""

    evidence = _read(mirrored_root, EVIDENCE_PATH)
    for record in evidence["automatic_approval_additions"]:
        record["license_text_authority"].pop("repository_path")
    _write(mirrored_root, EVIDENCE_PATH, evidence)

    assert not license_compliance_authority(mirrored_root).is_automatically_approved("PSF-2.0")


def test_tier_one_license_text_digest_is_recomputed(mirrored_root: Path) -> None:
    """A fabricated digest cannot unlock a beyond-baseline approval."""

    evidence = _read(mirrored_root, EVIDENCE_PATH)
    for record in evidence["automatic_approval_additions"]:
        record["license_text_authority"]["sha256"] = "a" * 64
    _write(mirrored_root, EVIDENCE_PATH, evidence)

    assert not license_compliance_authority(mirrored_root).is_automatically_approved("PSF-2.0")


def test_tier_one_license_text_byte_count_is_enforced(mirrored_root: Path) -> None:
    evidence = _read(mirrored_root, EVIDENCE_PATH)
    for record in evidence["automatic_approval_additions"]:
        record["license_text_authority"]["bytes"] = 1
    _write(mirrored_root, EVIDENCE_PATH, evidence)

    assert not license_compliance_authority(mirrored_root).is_automatically_approved("PSF-2.0")


def test_tier_one_license_text_must_stay_inside_the_repository(mirrored_root: Path) -> None:
    evidence = _read(mirrored_root, EVIDENCE_PATH)
    for record in evidence["automatic_approval_additions"]:
        record["license_text_authority"]["repository_path"] = "../outside/LICENSE"
    _write(mirrored_root, EVIDENCE_PATH, evidence)

    assert not license_compliance_authority(mirrored_root).is_automatically_approved("PSF-2.0")


def test_a_deleted_license_text_withdraws_the_approval(mirrored_root: Path) -> None:
    (mirrored_root / LICENSE_TEXT_PATH).unlink()
    assert not license_compliance_authority(mirrored_root).is_automatically_approved("PSF-2.0")


def test_editing_evidence_invalidates_compliance_identity(mirrored_root: Path) -> None:
    """Swapping the justification must not leave records verifiable."""

    baseline = license_compliance_authority(mirrored_root).policy_sha256

    evidence = _read(mirrored_root, EVIDENCE_PATH)
    evidence["automatic_approval_additions"][0]["verified_on_host"] = "SOMEWHERE-ELSE"
    _write(mirrored_root, EVIDENCE_PATH, evidence)

    assert license_compliance_authority(mirrored_root).policy_sha256 != baseline


def test_the_committed_license_text_matches_its_recorded_digest() -> None:
    evidence = json.loads((REPO_ROOT / EVIDENCE_PATH).read_text(encoding="utf-8"))
    for record in evidence["automatic_approval_additions"]:
        authority = record["license_text_authority"]
        payload = (REPO_ROOT / authority["repository_path"]).read_bytes()
        assert len(payload) == authority["bytes"]
        assert hashlib.sha256(payload).hexdigest() == authority["sha256"]


def test_baseline_approvals_do_not_require_evidence(mirrored_root: Path) -> None:
    evidence = _read(mirrored_root, EVIDENCE_PATH)
    evidence["automatic_approval_additions"] = []
    _write(mirrored_root, EVIDENCE_PATH, evidence)

    authority = license_compliance_authority(mirrored_root)
    for expression in sorted(BASELINE_AUTOMATIC_APPROVAL_SPDX):
        assert authority.is_automatically_approved(expression), expression


def test_missing_evidence_document_withdraws_non_baseline_approvals(mirrored_root: Path) -> None:
    (mirrored_root / EVIDENCE_PATH).unlink()
    authority = license_compliance_authority(mirrored_root)
    assert not authority.is_automatically_approved("PSF-2.0")
    assert authority.automatic_approval_spdx <= BASELINE_AUTOMATIC_APPROVAL_SPDX


def test_distribution_scope_covers_everything_the_export_ships(mirrored_root: Path) -> None:
    """The shipped closure and the per-package view must both be enforced."""

    lock = _read(mirrored_root, LOCK_PATH)
    shipped = {str(name) for name in lock["closure"]["runtime"]}
    scope = release_distribution_scope(mirrored_root)
    versions = {package["name"]: package["version"] for package in lock["packages"]}
    for name in shipped:
        assert notice_key("python-package", name, versions[name]) in scope, name


def test_closure_desync_cannot_narrow_enforcement(mirrored_root: Path) -> None:
    lock = _read(mirrored_root, LOCK_PATH)
    shipped = sorted(str(name) for name in lock["closure"]["runtime"])
    victim = shipped[0]
    versions = {package["name"]: package["version"] for package in lock["packages"]}

    # Remove the per-package marker while the export still ships the package.
    for package in lock["packages"]:
        if package["name"] == victim:
            package["closure_groups"] = [
                group for group in package["closure_groups"] if group != "runtime"
            ]
    _write(mirrored_root, LOCK_PATH, lock)

    scope = release_distribution_scope(mirrored_root)
    assert notice_key("python-package", victim, versions[victim]) in scope, (
        "a package still present in the shipped closure must stay in scope"
    )


def test_resolver_reports_unverified_when_the_lock_no_longer_matches() -> None:
    """An unverified lock must not be reported as plain READY."""

    from project_pipeline.release_hardening.pre_admission import (
        evaluate_pre_admission_release_gate,
    )

    baseline = evaluate_pre_admission_release_gate(REPO_ROOT)
    assert baseline.resolver_lock_state == "READY"

    lock = REPO_ROOT / "uv.lock"
    original = lock.read_bytes()
    try:
        lock.write_bytes(original + b"\n# tamper\n")
        verdict = evaluate_pre_admission_release_gate(REPO_ROOT)
    finally:
        lock.write_bytes(original)

    assert verdict.resolver_lock_state == "READY_UNVERIFIED"
    assert any("resolver lock is not verified" in blocker for blocker in verdict.blockers)
    assert evaluate_pre_admission_release_gate(REPO_ROOT).resolver_lock_state == "READY"


def test_both_closure_views_agree_in_the_committed_lock() -> None:
    """Drift between the two views should surface as a test failure."""

    lock = json.loads((REPO_ROOT / LOCK_PATH).read_text(encoding="utf-8"))
    shipped = {str(name) for name in lock["closure"]["runtime"]}
    marked = {
        package["name"]
        for package in lock["packages"]
        if "runtime" in (package.get("closure_groups") or [])
    }
    assert shipped == marked, f"closure desync: {shipped ^ marked}"
