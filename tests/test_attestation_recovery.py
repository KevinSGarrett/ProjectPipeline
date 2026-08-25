from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from project_pipeline.lifecycle import attestation_recovery as attestation_recovery_module
from project_pipeline.lifecycle.attestation_recovery import (
    EXPECTED_PUBLIC_ATTESTATION_BYTES,
    EXPECTED_PUBLIC_ATTESTATION_SHA256,
    EXPECTED_PUBLIC_QUALIFICATION_BYTES,
    EXPECTED_PUBLIC_QUALIFICATION_SHA256,
    PUBLIC_ATTESTATION_REF,
    PUBLIC_QUALIFICATION_REF,
    CurrentAttestationPolicy,
    RecoveryError,
    bootstrap_machine_local_attestation_records,
    evaluate_attestation_recovery,
    import_exact_public_artifact,
    recover_and_restore,
    resolve_durable_dir,
    sha256_bytes,
)
from tests.pp379_recovery_support import (
    durable_dir,
    historical_receipt,
    isolated_repo,
    source_root,
    write_json,
)


def test_preserved_public_bytes_match_expected_digests() -> None:
    attestation = (source_root() / PUBLIC_ATTESTATION_REF).read_bytes()
    qualification = (source_root() / PUBLIC_QUALIFICATION_REF).read_bytes()
    assert len(attestation) == EXPECTED_PUBLIC_ATTESTATION_BYTES
    assert len(qualification) == EXPECTED_PUBLIC_QUALIFICATION_BYTES
    assert sha256_bytes(attestation) == EXPECTED_PUBLIC_ATTESTATION_SHA256
    assert sha256_bytes(qualification) == EXPECTED_PUBLIC_QUALIFICATION_SHA256


def test_current_policy_accepts_exact_preserved_bytes(tmp_path: Path) -> None:
    evaluation = evaluate_attestation_recovery(
        repository_root=source_root(),
        source_attestation=source_root() / PUBLIC_ATTESTATION_REF,
        source_qualification=source_root() / PUBLIC_QUALIFICATION_REF,
        durable_attestation_path=durable_dir() / "privacy_attestation.json",
        durable_qualification_path=durable_dir() / "provider_qualification.json",
        verification_dir=tmp_path / "verify",
        historical_receipt_path=historical_receipt(),
    )
    by_kind = {item["kind"]: item for item in evaluation["artifacts"]}
    assert evaluation["accepted_for_restore"] is True
    assert by_kind["privacy_attestation"]["disposition"] == "RECOVERED_VALID"
    assert by_kind["provider_qualification"]["disposition"] == "RECOVERED_VALID"
    assert by_kind["privacy_attestation"]["current_policy_state"] == "VALID"
    assert by_kind["provider_qualification"]["current_policy_state"] == "VALID"
    assert by_kind["privacy_attestation"]["historical_receipt_match"] is True
    assert by_kind["provider_qualification"]["historical_receipt_match"] is True
    assert by_kind["privacy_attestation"]["durable_record_match"] is True
    assert by_kind["provider_qualification"]["durable_record_match"] is True


def test_import_rejects_mismatched_bytes(tmp_path: Path) -> None:
    source = tmp_path / "forged.json"
    source.write_text('{"approved": true}', encoding="utf-8")
    with pytest.raises(RecoveryError):
        import_exact_public_artifact(
            source=source,
            destination=tmp_path / "dest.json",
            expected_sha256=EXPECTED_PUBLIC_ATTESTATION_SHA256,
            expected_byte_length=EXPECTED_PUBLIC_ATTESTATION_BYTES,
        )


def test_copying_arbitrary_json_to_expected_path_is_not_recovery(tmp_path: Path) -> None:
    forged = tmp_path / "forged.json"
    write_json(
        forged,
        {
            "project_id": "PROJECT-PIPELINE",
            "provider_id": "provider:cursor-cli",
            "scope": "local-governed-phase1",
            "approved": True,
            "approved_at_utc": "2026-08-16T22:00:00+00:00",
        },
    )
    dest = tmp_path / PUBLIC_ATTESTATION_REF
    dest.parent.mkdir(parents=True)
    dest.write_bytes(forged.read_bytes())
    assert sha256_bytes(dest.read_bytes()) != EXPECTED_PUBLIC_ATTESTATION_SHA256
    with pytest.raises(RecoveryError):
        import_exact_public_artifact(
            source=forged,
            destination=tmp_path / "other.json",
            expected_sha256=EXPECTED_PUBLIC_ATTESTATION_SHA256,
            expected_byte_length=EXPECTED_PUBLIC_ATTESTATION_BYTES,
        )


def test_restore_is_idempotent_and_refuses_overwrite(tmp_path: Path) -> None:
    repo = isolated_repo(tmp_path)
    first = recover_and_restore(
        repository_root=repo,
        source_root=source_root(),
        durable_dir=durable_dir(),
        verification_dir=tmp_path / "verify",
        apply=True,
    )
    assert first["applied"] is True
    restored = (repo / PUBLIC_ATTESTATION_REF).read_bytes()
    assert sha256_bytes(restored) == EXPECTED_PUBLIC_ATTESTATION_SHA256
    second = recover_and_restore(
        repository_root=repo,
        source_root=source_root(),
        durable_dir=durable_dir(),
        verification_dir=tmp_path / "verify2",
        apply=True,
    )
    assert second["restore"]["attestation_import"]["idempotent"] is True
    (repo / PUBLIC_ATTESTATION_REF).write_text('{"forged": true}', encoding="utf-8")
    with pytest.raises(RecoveryError):
        recover_and_restore(
            repository_root=repo,
            source_root=source_root(),
            durable_dir=durable_dir(),
            verification_dir=tmp_path / "verify3",
            apply=True,
        )


def test_missing_source_is_missing_not_valid(tmp_path: Path) -> None:
    evaluation = evaluate_attestation_recovery(
        repository_root=tmp_path,
        source_attestation=tmp_path / "absent-att.json",
        source_qualification=tmp_path / "absent-qual.json",
        durable_attestation_path=tmp_path / "absent-durable-att.json",
        durable_qualification_path=tmp_path / "absent-durable-qual.json",
        verification_dir=tmp_path / "verify",
    )
    assert evaluation["accepted_for_restore"] is False
    assert {item["disposition"] for item in evaluation["artifacts"]} == {"MISSING"}


def test_stale_policy_is_not_collapsed_into_valid(tmp_path: Path) -> None:
    evaluation = evaluate_attestation_recovery(
        repository_root=source_root(),
        source_attestation=source_root() / PUBLIC_ATTESTATION_REF,
        source_qualification=source_root() / PUBLIC_QUALIFICATION_REF,
        durable_attestation_path=durable_dir() / "privacy_attestation.json",
        durable_qualification_path=durable_dir() / "provider_qualification.json",
        verification_dir=tmp_path / "verify",
        historical_receipt_path=historical_receipt(),
        policy=CurrentAttestationPolicy(max_age_hours=1),
    )
    by_kind = {item["kind"]: item for item in evaluation["artifacts"]}
    assert evaluation["accepted_for_restore"] is False
    assert by_kind["privacy_attestation"]["disposition"] == "RECOVERED_BUT_STALE"
    assert by_kind["privacy_attestation"]["current_policy_state"] != "VALID"


def test_invalid_timestamp_is_not_valid(tmp_path: Path) -> None:
    durable = tmp_path / "durable"
    durable.mkdir()
    payload = json.loads((durable_dir() / "privacy_attestation.json").read_text(encoding="utf-8"))
    payload["approved_at_utc"] = "not-a-timestamp"
    write_json(durable / "privacy_attestation.json", payload)
    shutil_copy = durable_dir() / "provider_qualification.json"
    (durable / "provider_qualification.json").write_bytes(shutil_copy.read_bytes())
    evaluation = evaluate_attestation_recovery(
        repository_root=source_root(),
        source_attestation=source_root() / PUBLIC_ATTESTATION_REF,
        source_qualification=source_root() / PUBLIC_QUALIFICATION_REF,
        durable_attestation_path=durable / "privacy_attestation.json",
        durable_qualification_path=durable / "provider_qualification.json",
        verification_dir=tmp_path / "verify",
        historical_receipt_path=historical_receipt(),
        policy=CurrentAttestationPolicy(max_age_hours=24),
    )
    by_kind = {item["kind"]: item for item in evaluation["artifacts"]}
    assert evaluation["accepted_for_restore"] is False
    assert "missing_or_invalid_timestamp" in by_kind["privacy_attestation"]["validator_reasons"]
    assert by_kind["privacy_attestation"]["current_policy_state"] != "VALID"


def test_resolve_durable_dir_honors_explicit(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    assert resolve_durable_dir(tmp_path / "repo", explicit) == explicit


def test_resolve_durable_dir_prefers_canonical_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = tmp_path / "canonical"
    write_json(canonical / "privacy_attestation.json", {"ok": True})
    write_json(canonical / "provider_qualification.json", {"ok": True})
    monkeypatch.setattr(attestation_recovery_module, "DEFAULT_DURABLE_DIR", canonical)
    repo = tmp_path / "worktree"
    assert attestation_recovery_module.resolve_durable_dir(repo, None) == canonical


def test_resolve_durable_dir_falls_back_to_repo_when_canonical_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        attestation_recovery_module, "DEFAULT_DURABLE_DIR", tmp_path / "missing-canonical"
    )
    repo = tmp_path / "worktree"
    assert attestation_recovery_module.resolve_durable_dir(repo, None) == (
        repo / ".local" / "state" / "takeover"
    )


def test_bootstrap_creates_verified_machine_local_records_without_importing_private_state(
    tmp_path: Path,
) -> None:
    repo = isolated_repo(tmp_path)
    for reference in (PUBLIC_ATTESTATION_REF, PUBLIC_QUALIFICATION_REF):
        source = source_root() / reference
        destination = repo / reference
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    durable = repo / ".local" / "state" / "takeover"
    first = bootstrap_machine_local_attestation_records(
        repository_root=repo,
        durable_dir=durable,
        verification_dir=tmp_path / "verify-first",
    )
    assert first["cross_machine_state_imported"] is False
    assert first["evaluation"]["accepted_for_restore"] is True
    assert first["writes"]["privacy_attestation"]["applied"] is True
    assert first["writes"]["provider_qualification"]["applied"] is True
    second = bootstrap_machine_local_attestation_records(
        repository_root=repo,
        durable_dir=durable,
        verification_dir=tmp_path / "verify-second",
    )
    assert second["evaluation"]["accepted_for_restore"] is True
    assert second["writes"]["privacy_attestation"]["applied"] is False
    assert second["writes"]["provider_qualification"]["applied"] is False


def test_bootstrap_refuses_to_replace_mismatched_machine_local_record(tmp_path: Path) -> None:
    repo = isolated_repo(tmp_path)
    for reference in (PUBLIC_ATTESTATION_REF, PUBLIC_QUALIFICATION_REF):
        source = source_root() / reference
        destination = repo / reference
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    durable = repo / ".local" / "state" / "takeover"
    write_json(durable / "privacy_attestation.json", {"forged": True})
    with pytest.raises(RecoveryError, match="refusing to replace"):
        bootstrap_machine_local_attestation_records(
            repository_root=repo,
            durable_dir=durable,
            verification_dir=tmp_path / "verify",
        )
    assert json.loads((durable / "privacy_attestation.json").read_text(encoding="utf-8")) == {
        "forged": True
    }
    assert not (durable / "provider_qualification.json").exists()


def test_bootstrap_default_ignores_populated_canonical_coordinator_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = isolated_repo(tmp_path)
    for reference in (PUBLIC_ATTESTATION_REF, PUBLIC_QUALIFICATION_REF):
        source = source_root() / reference
        destination = repo / reference
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    canonical = tmp_path / "coordinator-state"
    canonical.mkdir(parents=True, exist_ok=True)
    for filename in ("privacy_attestation.json", "provider_qualification.json"):
        shutil.copy2(durable_dir() / filename, canonical / filename)
    original = {
        filename: (canonical / filename).read_bytes()
        for filename in ("privacy_attestation.json", "provider_qualification.json")
    }
    monkeypatch.setattr(attestation_recovery_module, "DEFAULT_DURABLE_DIR", canonical)

    result = bootstrap_machine_local_attestation_records(
        repository_root=repo,
        verification_dir=tmp_path / "verify",
    )

    target = repo / ".local" / "state" / "takeover"
    assert result["durable_dir"] == str(target.resolve())
    assert result["cross_machine_state_imported"] is False
    assert (target / "privacy_attestation.json").is_file()
    assert (target / "provider_qualification.json").is_file()
    assert {
        filename: (canonical / filename).read_bytes()
        for filename in ("privacy_attestation.json", "provider_qualification.json")
    } == original


def test_bootstrap_refuses_explicit_durable_dir_outside_worker_local_state(tmp_path: Path) -> None:
    with pytest.raises(RecoveryError, match=r"must be within repository_root/.local"):
        bootstrap_machine_local_attestation_records(
            repository_root=source_root(),
            durable_dir=tmp_path / "other-machine-state",
            verification_dir=tmp_path / "verify",
        )
