from __future__ import annotations

import json
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.cli import _run_security_command
from project_pipeline.configuration.loader import ConfigurationError
from project_pipeline.security.artifact_binding import ArtifactBindingStore, artifact_digest


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "artifact_id": "ART-1",
        "sbom_sha256": "s" * 64,
        "license_result_sha256": "l" * 64,
        "vulnerability_result_sha256": "v" * 64,
        "provenance_sha256": "p" * 64,
        "signer_identity_id": "ID-1",
        "approval_id": "APR-1",
        "build_id": "BLD-1",
        "release_decision": "ALLOW",
        "expires_at_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    base.update(overrides)
    return base


def test_bind_replay_conflict_revoke_and_query(tmp_path: Path) -> None:
    store = ArtifactBindingStore(tmp_path / "bindings.db")
    first = store.bind(_payload())
    replay = store.bind(_payload())
    assert first["digest"] == replay["digest"]
    assert replay["replayed"] is True
    assert first["digest"] == artifact_digest(_payload())
    with pytest.raises(ValueError, match="conflicting"):
        store.bind(_payload(release_decision="DENY"))
    with pytest.raises(ValueError, match="secret-shaped"):
        store.bind(_payload(token="sk-abcdefghijklmnopqrstuvwxyz"))
    with pytest.raises(ValueError, match="missing binding fields"):
        store.bind({"artifact_id": "ART-2"})
    with pytest.raises(ValueError, match="expired"):
        store.bind(_payload(expires_at_utc=(datetime.now(UTC) - timedelta(hours=1)).isoformat()))
    verified = store.verify(_payload())
    assert verified["verified"] is True
    revoked = store.revoke(first["binding_id"])
    assert revoked["revoked"] is True
    with pytest.raises(ValueError, match="revoked"):
        store.verify(_payload())
    assert store.audit(first["binding_id"])[-1]["action"] == "REVOKE"
    with pytest.raises(ValueError, match="limit"):
        store.query(limit=1000)
    rows = store.query(limit=10)
    assert rows[0]["digest"]
    assert "secret" not in json.dumps(rows)
    store.close()


def test_cli_requires_approval_and_bounds_queries(tmp_path: Path, project_root: Path) -> None:
    payload_path = tmp_path / "binding.json"
    payload_path.write_text(json.dumps(_payload()), encoding="utf-8")
    denied = Namespace(
        action="bind-artifact",
        root=project_root,
        database=tmp_path / "bindings.db",
        input=payload_path,
        apply=False,
        approve=False,
        binding_id=None,
        limit=20,
        offset=0,
        json_output=None,
    )
    with pytest.raises(ConfigurationError, match="requires --apply --approve"):
        _run_security_command(denied)
    allowed = Namespace(
        action="bind-artifact",
        root=project_root,
        database=tmp_path / "bindings.db",
        input=payload_path,
        apply=True,
        approve=True,
        binding_id=None,
        limit=20,
        offset=0,
        json_output=None,
    )
    result, code = _run_security_command(allowed)
    assert code == 0
    assert result["artifact_binding"]["digest"]
    listed, code = _run_security_command(
        Namespace(
            action="artifact-bindings",
            root=project_root,
            database=tmp_path / "bindings.db",
            input=None,
            apply=False,
            approve=False,
            binding_id=None,
            limit=20,
            offset=0,
            json_output=None,
        )
    )
    assert code == 0
    assert listed["artifact_bindings"]
    with pytest.raises(ValueError, match="limit"):
        _run_security_command(
            Namespace(
                action="artifact-bindings",
                root=project_root,
                database=tmp_path / "bindings.db",
                input=None,
                apply=False,
                approve=False,
                binding_id=None,
                limit=5000,
                offset=0,
                json_output=None,
            )
        )
