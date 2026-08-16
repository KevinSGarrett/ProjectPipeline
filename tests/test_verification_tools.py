from pathlib import Path

import pytest

from project_pipeline.verification.external_tools import (
    AxeCoreProfile,
    SchemathesisAdapter,
    VerificationToolUnavailable,
)
from project_pipeline.verification.tools import activation_snapshot


def test_activation_snapshot_covers_exact_13_candidates(project_root: Path):
    rows = activation_snapshot(project_root)
    assert len(rows) == 13
    assert len({item.upstream_id for item in rows}) == 13


def test_playwright_environment_is_observed_if_installed(project_root: Path):
    rows = {item.upstream_id: item for item in activation_snapshot(project_root)}
    row = rows["UPSTREAM-063"]
    assert "src/project_pipeline/verification/browser.py" in row.integration_paths


def test_schemathesis_adapter_rejects_external_schema(project_root: Path, tmp_path: Path):
    outside = tmp_path / "schema.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises((ValueError, VerificationToolUnavailable)):
        SchemathesisAdapter().build(project_root, schema=outside, base_url="http://127.0.0.1:8000")


def test_axe_bundle_must_be_repository_local(project_root: Path, tmp_path: Path):
    bundle = tmp_path / "axe.js"
    bundle.write_text("// no-op", encoding="utf-8")
    with pytest.raises(ValueError):
        AxeCoreProfile().validate_bundle(project_root, bundle)
