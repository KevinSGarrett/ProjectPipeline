from pathlib import Path

import pytest

from project_pipeline.upstream_integrations.security import (
    AgeAdapter,
    ConftestAdapter,
    OpaAdapter,
    ScorecardAdapter,
    SopsAdapter,
    TrivyAdapter,
)


def test_trivy_offline_scan_is_safe(project_root):
    p = TrivyAdapter().plan_filesystem_scan(project_root, offline=True)
    assert (
        p.upstream_id == "UPSTREAM-007"
        and p.network_required is False
        and "--offline-scan" in p.argv
        and "--disable-telemetry" in p.argv
    )


def test_trivy_rejects_unknown_scanner(project_root):
    with pytest.raises(ValueError):
        TrivyAdapter().plan_filesystem_scan(project_root, scanners=("vuln", "bogus"))


def test_trivy_sbom_format(project_root):
    p = TrivyAdapter().plan_sbom(project_root, format="cyclonedx", offline=True)
    assert "cyclonedx" in p.argv


def test_opa_plan_uses_stdin(project_root):
    p = OpaAdapter().plan_eval(
        project_root,
        policy_dir=Path("policies/security"),
        query="data.project_pipeline.security.allow",
        input_document={"authorized": True},
    )
    assert "--stdin-input" in p.argv and p.stdin and p.output_format == "json"


def test_conftest_confines_target(project_root):
    p = ConftestAdapter().plan_test(
        project_root,
        target=Path("config/security_policy.json"),
        policy_dir=Path("policies/security"),
    )
    assert Path(p.argv[-1]) == (project_root / "config/security_policy.json").resolve()
    with pytest.raises(ValueError):
        ConftestAdapter().plan_test(
            project_root, target=Path("../outside"), policy_dir=Path("policies/security")
        )


def test_scorecard_requires_github_https(project_root):
    p = ScorecardAdapter().plan_repository_scan(
        project_root, "https://github.com/KevinSGarrett/ProjectPipeline"
    )
    assert p.network_required
    with pytest.raises(ValueError):
        ScorecardAdapter().plan_repository_scan(project_root, "http://example.com/x")


def test_sops_and_age_mark_plaintext_runtime_only(project_root, tmp_path):
    enc = project_root / "config/security_policy.json"
    identity = tmp_path / "id"
    identity.write_text("x")
    assert (
        SopsAdapter().plan_decrypt(project_root, enc).output_format
        == "secret-plaintext-runtime-only"
    )
    assert (
        AgeAdapter()
        .plan_decrypt(project_root, enc, identity_file=identity)
        .metadata["plaintext_persistence_allowed"]
        is False
    )
