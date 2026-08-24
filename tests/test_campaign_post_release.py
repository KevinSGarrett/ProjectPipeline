from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from project_pipeline.release_factory.lifecycle import write_acquired_assets

ROOT = Path(__file__).resolve().parents[1]


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "campaign_post_release_verifier", ROOT / "scripts" / "verify_campaign_post_release.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_post_release_binding_rejects_stale_or_unbound_remote_artifacts(tmp_path: Path):
    verifier = _load_verifier()
    payload = b"remote-release-bytes"
    name = "project-pipeline-a.zip"
    digest = hashlib.sha256(payload).hexdigest()
    acquired = write_acquired_assets(tmp_path / "acquired", {name: payload})
    (acquired / "campaign_publication.json").write_text(
        json.dumps(
            {
                "state": "PUBLISHED",
                "provider": "github-rest",
                "source_sha": "a" * 40,
                "source_tree": "b" * 40,
                "assets": [
                    {
                        "name": name,
                        "sha256": digest,
                        "remote_sha256": digest,
                        "bytes_verified": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert verifier._publication_binding(acquired, expected_sha="a" * 40, expected_tree="b" * 40)[
        "expected_assets"
    ] == {name: digest}
    (acquired / "old-project-pipeline.zip").write_bytes(b"stale")
    with pytest.raises(ValueError, match="unexpected files"):
        verifier._publication_binding(acquired, expected_sha="a" * 40, expected_tree="b" * 40)
