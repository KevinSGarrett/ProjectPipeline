from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from project_pipeline.resilience.backup import build_integrity_manifest
from project_pipeline.resilience.restore import (
    RestoreIntentStore,
    RestoreTargetPolicy,
    verify_restored_tree,
)


def test_restore_policy_rejects_unsafe_targets(tmp_path, project_root):
    allow = tmp_path / "isolate"
    allow.mkdir()
    policy = RestoreTargetPolicy([allow], workspace_roots=[project_root])
    safe = allow / "restore-a"
    safe.mkdir()
    assert policy.resolve(safe) == safe.resolve()
    with pytest.raises(ValueError):
        policy.resolve("")
    with pytest.raises(ValueError):
        policy.resolve("relative/path")
    with pytest.raises(ValueError):
        policy.resolve(str(allow / ".." / "escape"))
    with pytest.raises(ValueError):
        policy.resolve("C:/")
    with pytest.raises(ValueError):
        policy.resolve("C:\\")
    with pytest.raises(ValueError):
        policy.resolve("\\\\server\\share\\restore")
    with pytest.raises(ValueError):
        policy.resolve(project_root)
    with pytest.raises(ValueError):
        policy.resolve(tmp_path / "outside")
    with pytest.raises(ValueError):
        RestoreTargetPolicy([Path("C:/")])
    with pytest.raises(ValueError):
        RestoreTargetPolicy([Path("/")])
    with pytest.raises(ValueError):
        policy.resolve("/")
    link = allow / "final-link"
    try:
        link.symlink_to(safe, target_is_directory=True)
    except OSError:
        link = None
    if link is not None:
        with pytest.raises(ValueError, match=r"reparse|escape"):
            policy.resolve(link)
        with pytest.raises(ValueError, match=r"reparse|escape"):
            policy.resolve(link / "ghost")


def test_restore_policy_rejects_workspace_and_protected_paths(tmp_path, project_root):
    policy = RestoreTargetPolicy([tmp_path], workspace_roots=[project_root])
    with pytest.raises(ValueError):
        policy.resolve(project_root / "src")
    if os.name == "nt":
        with pytest.raises(ValueError):
            policy.resolve(Path("C:/Windows/System32"))


def test_restore_policy_rejects_final_link_even_if_destination_is_inside_allowlist(
    tmp_path, project_root, monkeypatch
):
    allow = tmp_path / "isolate"
    allow.mkdir()
    inside = allow / "inside"
    inside.mkdir()
    link = allow / "final-link"
    monkeypatch.setattr(
        "project_pipeline.resilience.restore._is_reparse",
        lambda path: Path(path) == link or Path(path).name == "final-link",
    )
    policy = RestoreTargetPolicy([allow], workspace_roots=[project_root])
    with pytest.raises(ValueError, match=r"reparse|escape"):
        policy.resolve(link)
    with pytest.raises(ValueError, match=r"reparse|escape"):
        policy.resolve(link / "ghost")


def test_restore_policy_rejects_reparse_escape_when_supported(tmp_path, project_root):
    allow = tmp_path / "isolate"
    allow.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = allow / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links or junctions are unavailable in this environment")
    policy = RestoreTargetPolicy([allow], workspace_roots=[project_root])
    with pytest.raises(ValueError, match=r"reparse|outside|escape"):
        policy.resolve(link / "nested")


def test_integrity_verification_reports_missing_extra_and_corrupt(tmp_path):
    target = tmp_path / "restored"
    target.mkdir()
    good = target / "state.db"
    good.write_bytes(b"ok")
    extra = target / "extra.bin"
    extra.write_bytes(b"nope")
    manifest = build_integrity_manifest(
        [
            {
                "path": "state.db",
                "sha256": hashlib.sha256(b"ok").hexdigest(),
                "size_bytes": 2,
            },
            {
                "path": "missing.json",
                "sha256": "a" * 64,
                "size_bytes": 1,
            },
        ]
    )
    result = verify_restored_tree(target, manifest)
    assert result["state"] == "VERIFY_FAILED"
    assert result["missing"] == ["missing.json"]
    assert result["extra"] == ["extra.bin"]
    good.write_bytes(b"bad")
    corrupt_manifest = build_integrity_manifest(
        [
            {
                "path": "state.db",
                "sha256": hashlib.sha256(b"ok").hexdigest(),
                "size_bytes": 2,
            }
        ]
    )
    (target / "extra.bin").unlink()
    corrupt = verify_restored_tree(target, corrupt_manifest)
    assert corrupt["corrupt"] == ["state.db"]


def test_restore_intent_idempotency_apply_and_verify(tmp_path, project_root):
    allow = tmp_path / "isolate"
    source = tmp_path / "backup"
    target = allow / "restored"
    allow.mkdir()
    payload = b"canonical-state"
    entry_path = source / "state.db"
    entry_path.parent.mkdir(parents=True)
    entry_path.write_bytes(payload)
    manifest = build_integrity_manifest(
        [
            {
                "path": "state.db",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        ]
    )
    policy = RestoreTargetPolicy([allow], workspace_roots=[project_root])
    store = RestoreIntentStore(tmp_path / "restore.sqlite3")
    first = store.record_intent(
        idempotency_key="restore-1",
        domain="canonical_state",
        target=target,
        manifest_sha256=str(manifest["aggregate_sha256"]),
    )
    replay = store.record_intent(
        idempotency_key="restore-1",
        domain="canonical_state",
        target=target,
        manifest_sha256=str(manifest["aggregate_sha256"]),
    )
    assert replay["replayed"] is True
    with pytest.raises(ValueError, match="conflicting"):
        store.record_intent(
            idempotency_key="restore-1",
            domain="artifacts",
            target=target,
            manifest_sha256=str(manifest["aggregate_sha256"]),
        )
    dry = store.dry_run(first["intent_id"], policy)
    assert dry["state"] == "DRY_RUN_COMPLETE"
    with pytest.raises(ValueError, match="approval"):
        store.apply(first["intent_id"], source=source, policy=policy, approve=False)
    applied = store.apply(first["intent_id"], source=source, policy=policy, approve=True)
    assert applied["state"] == "APPLIED"
    verified = store.verify(first["intent_id"], manifest, policy)
    assert verified["state"] == "VERIFY_PASSED"
    assert verified["restore_state"] == "VERIFIED"
    store.close()


def test_restore_unknown_outcome_reconciles_before_retry(tmp_path, project_root, monkeypatch):
    allow = tmp_path / "isolate"
    source = tmp_path / "backup"
    allow.mkdir()
    source.mkdir()
    (source / "state.db").write_bytes(b"x")
    target = allow / "partial"
    policy = RestoreTargetPolicy([allow], workspace_roots=[project_root])
    store = RestoreIntentStore(tmp_path / "restore.sqlite3")
    recorded = store.record_intent(
        idempotency_key="restore-unknown",
        domain="evidence",
        target=target,
        manifest_sha256="b" * 64,
    )

    def boom(*_args, **_kwargs):
        raise OSError("interrupted restore")

    monkeypatch.setattr("project_pipeline.resilience.restore._copy_tree", boom)
    with pytest.raises(OSError):
        store.apply(recorded["intent_id"], source=source, policy=policy, approve=True)
    assert store.get(recorded["intent_id"])["state"] == "UNKNOWN_OUTCOME"
    target.mkdir()
    reconciled = store.reconcile(recorded["intent_id"])
    assert reconciled["state"] == "RECONCILED"
    store.close()
