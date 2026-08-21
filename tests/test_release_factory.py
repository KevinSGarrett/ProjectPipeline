from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest

from project_pipeline.cli import _run_release_factory_command, main
from project_pipeline.configuration import ConfigurationError
from project_pipeline.contracts import ActionIntent, AdapterErrorCategory, ApprovalState, RiskLevel
from project_pipeline.github_steward import GitHubDraftReleaseService, GitHubStewardStore
from project_pipeline.github_steward.errors import GitHubStewardError
from project_pipeline.github_steward.mock import MockGitHubAdapter
from project_pipeline.release_factory import (
    BLOCKED_EXTERNAL_SIGNING_IDENTITY_MISSING,
    MIXED_HEAD,
    VERSION_SOURCE_MISMATCH,
    bind_bundle_supply_chain,
    build_release_bundle,
    exercise_acquired_lifecycle,
    extract_zip_safely,
    resolve_release_version_authority,
    write_acquired_assets,
    write_fixture_artifacts,
)
from project_pipeline.release_factory.bundle import BoundArtifact, ReleaseBundle
from project_pipeline.release_factory.supply import _os_path, _scan_secrets

ROOT = Path(__file__).resolve().parents[1]


def _write_version_tree(repo: Path, *, python: str = "0.9.0", desktop: str = "0.10.0") -> None:
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "project-pipeline"\nversion = "{python}"\n',
        encoding="utf-8",
    )
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "version_compatibility.json").write_text(
        json.dumps({"platform_version": python, "schema_version": "1.0.0"}) + "\n",
        encoding="utf-8",
    )
    (repo / "src/project_pipeline").mkdir(parents=True)
    (repo / "src/project_pipeline/__init__.py").write_text(
        f'__version__ = "{python}"\n', encoding="utf-8"
    )
    (repo / "apps/command_center").mkdir(parents=True)
    (repo / "apps/command_center/package.json").write_text(
        json.dumps({"name": "command-center", "version": desktop}) + "\n", encoding="utf-8"
    )
    (repo / "apps/desktop_shell/src-tauri").mkdir(parents=True)
    (repo / "apps/desktop_shell/src-tauri/tauri.conf.json").write_text(
        json.dumps({"version": desktop}) + "\n", encoding="utf-8"
    )
    (repo / "apps/desktop_shell/src-tauri/Cargo.toml").write_text(
        f'[package]\nname = "desktop_shell"\nversion = "{desktop}"\n',
        encoding="utf-8",
    )


def _git_repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "candidate"], check=True, capture_output=True
    )
    return path


def test_version_authority_reads_current_repository():
    authority = resolve_release_version_authority(ROOT)
    assert authority.bundle_version == "0.9.0"
    assert authority.desktop_version == "0.10.0"
    assert authority.dual_identity is True
    assert authority.tag_name.startswith("v0.9.0-rc.")
    assert len(authority.source_sha) == 40


def test_python_version_mismatch_fails_closed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_version_tree(repo, python="0.9.0")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "project-pipeline"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    _git_repo(repo)
    with pytest.raises(ValueError, match=VERSION_SOURCE_MISMATCH):
        resolve_release_version_authority(repo)


def test_desktop_version_mismatch_fails_closed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_version_tree(repo, desktop="0.10.0")
    (repo / "apps/command_center/package.json").write_text(
        json.dumps({"version": "9.9.9"}) + "\n", encoding="utf-8"
    )
    _git_repo(repo)
    with pytest.raises(ValueError, match=VERSION_SOURCE_MISMATCH):
        resolve_release_version_authority(repo)


def test_bundle_is_content_addressed_resumable_and_rejects_mixed_head(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_version_tree(repo)
    _git_repo(repo)
    dest = tmp_path / "out"
    first = build_release_bundle(repo, dest, fixture_desktop=True, use_git_archive=False)
    second = build_release_bundle(repo, dest, fixture_desktop=True, use_git_archive=False)
    assert second.resumable is True
    assert first.cache_key == second.cache_key
    assert first.desktop_bound is True
    poisoned = Path(first.output_dir) / first.artifacts[0].name
    sidecar = poisoned.with_suffix(poisoned.suffix + ".candidate.json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["source_sha"] = "c" * 40
    sidecar.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (Path(first.output_dir) / "candidate.json").unlink()
    with pytest.raises(ValueError, match=MIXED_HEAD):
        build_release_bundle(repo, dest, fixture_desktop=True, use_git_archive=False)


def test_supply_binding_extracts_cleanly_and_records_missing_signing(tmp_path):
    authority = resolve_release_version_authority(ROOT)
    dest = tmp_path / "bundle"
    paths = write_fixture_artifacts(
        dest,
        version=authority,
        desktop_executable=b"MZ-exe",
        desktop_installer=b"MZ-msi",
    )
    artifacts = []
    for kind, path in paths.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append(
            BoundArtifact(
                kind=kind,
                name=path.name,
                sha256=digest,
                size_bytes=path.stat().st_size,
                source_sha=authority.source_sha,
                source_tree=authority.source_tree,
            )
        )
    bundle = ReleaseBundle(
        cache_key="a" * 64,
        version=authority,
        artifacts=tuple(artifacts),
        output_dir=str(dest),
        desktop_bound=True,
    )
    binding = bind_bundle_supply_chain(ROOT, bundle)
    assert binding.clean_extraction is True
    assert binding.secret_scan == "CLEAN"
    assert binding.authenticode_state == BLOCKED_EXTERNAL_SIGNING_IDENTITY_MISSING
    assert (dest / "sbom.json").is_file()


def test_zip_slip_and_secret_residue_are_rejected(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr("../evil.txt", "nope")
    with pytest.raises(ValueError, match="archive traversal"):
        extract_zip_safely(archive, tmp_path / "out")
    dest = tmp_path / "extract-root"
    dest.mkdir()
    prefix = tmp_path / "prefix.zip"
    with zipfile.ZipFile(prefix, "w") as payload:
        payload.writestr("../extract-root-evil/payload.txt", "escaped")
    with pytest.raises(ValueError, match="archive traversal"):
        extract_zip_safely(prefix, dest)
    assert not (tmp_path / "extract-root-evil").exists()
    secret_zip = tmp_path / "secret.zip"
    with zipfile.ZipFile(secret_zip, "w") as payload:
        payload.writestr("leak.txt", "BEGIN OPENSSH PRIVATE " + "KEY\n")
    written = extract_zip_safely(secret_zip, tmp_path / "secret-out")
    with pytest.raises(ValueError, match="secret residue"):
        _scan_secrets(written)
    detector = tmp_path / "registry.py"
    detector.write_text(
        r"(?i)(sk-[a-z0-9]{16,}|ghp_[a-z0-9]{20,}|xoxb-[a-z0-9-]{20,}|api[_-]?key\s*[:=]\s*\S+)",
        encoding="utf-8",
    )
    _scan_secrets((detector,))
    token_leak = tmp_path / "leak.env"
    token_leak.write_text("GITHUB_TOKEN=" + "ghp_" + ("A" * 36) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="secret residue"):
        _scan_secrets((token_leak,))


def test_extract_zip_safely_writes_windows_long_paths(tmp_path):
    dest = tmp_path / ("n" * 90) / ("n" * 90)
    archive = tmp_path / "long.zip"
    member = "payload/" + ("d" * 40) + "/" + ("f" * 40) + ".txt"
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr(member, "ok-long-path")
    written = extract_zip_safely(archive, dest)
    assert len(written) == 1
    assert _os_path(written[0]).read_text(encoding="utf-8") == "ok-long-path"


def test_git_archive_omits_export_ignored_dummy(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_version_tree(repo)
    (repo / ".gitattributes").write_text("dummy/ export-ignore\n", encoding="utf-8")
    nested = repo / "dummy" / "PPQS-pack"
    nested.mkdir(parents=True)
    (nested / "oracle.txt").write_text("oracle\n", encoding="utf-8")
    (repo / "README.md").write_text("ok\n", encoding="utf-8")
    _git_repo(repo)
    bundle = build_release_bundle(
        repo, tmp_path / "out", fixture_desktop=True, use_git_archive=True
    )
    archive = Path(bundle.output_dir) / f"project-pipeline-{bundle.version.source_sha[:12]}.zip"
    with zipfile.ZipFile(archive) as payload:
        names = tuple(name.replace("\\", "/") for name in payload.namelist())
    assert any(name.endswith("README.md") for name in names)
    assert not any("dummy/" in name or name.endswith("oracle.txt") for name in names)


def test_desktop_dir_fails_closed_without_exact_match(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_version_tree(repo)
    _git_repo(repo)
    empty = tmp_path / "desktop"
    empty.mkdir()
    with pytest.raises(ValueError, match="exactly one file"):
        build_release_bundle(repo, tmp_path / "out", desktop_artifact_dir=empty)


def test_draft_release_unknown_outcome_duplicate_and_finalize_guards(tmp_path):
    adapter = MockGitHubAdapter(repository_slug="owner/repo")
    db = tmp_path / "state.db"
    authority = resolve_release_version_authority(ROOT)
    dest = tmp_path / "bundle"
    paths = write_fixture_artifacts(
        dest,
        version=authority,
        desktop_executable=b"MZ-exe",
        desktop_installer=b"MZ-msi",
    )
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths.values()}
    with GitHubStewardStore(db, ROOT) as store:
        service = GitHubDraftReleaseService(remote=adapter, store=store)
        planned = service.plan_create_draft(
            "owner/repo",
            tag_name=authority.tag_name,
            name="draft",
            body="body",
            target_commitish=authority.source_sha,
            source_tree=authority.source_tree,
            artifact_sha256s=hashes,
            actor_id="actor:test",
            correlation_id="corr:test",
        )
        intent = ActionIntent(
            actor_id="actor:test",
            authority="github.steward",
            target="owner/repo",
            operation="github.draft-release.create",
            idempotency_key=planned.idempotency_key,
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:test",
            risk=RiskLevel.HIGH,
        )
        adapter.schedule_failure("create_draft_release", AdapterErrorCategory.UNKNOWN_OUTCOME)
        receipt = service.apply_create_draft(
            planned, action_intent=intent, authorization_id="auth:test"
        )
        assert receipt.reconciliation_required is True
        with pytest.raises(GitHubStewardError, match="unknown-outcome"):
            service.apply_create_draft(planned, action_intent=intent, authorization_id="auth:test")
        reconciled = service.reconcile_create_draft(planned)
        assert reconciled.state.value == "RECONCILED"
        release = adapter.get_release("owner/repo", int(reconciled.external_identifier))
        assert release is not None and release.draft is True
        name = next(iter(paths.values())).name
        content = next(iter(paths.values())).read_bytes()
        digest = hashes[name]
        upload = service.plan_upload_asset(
            "owner/repo",
            release_id=release.api_id,
            name=name,
            sha256=digest,
            source_sha=authority.source_sha,
            actor_id="actor:test",
            correlation_id="corr:test",
        )
        upload_intent = intent.model_copy(
            update={
                "operation": "github.draft-release.upload",
                "idempotency_key": upload.idempotency_key,
            }
        )
        uploaded = service.apply_upload_asset(
            upload,
            content=content,
            content_type="application/octet-stream",
            action_intent=upload_intent,
            authorization_id="auth:test",
        )
        assert uploaded.state.value == "APPLIED"
        with pytest.raises(GitHubStewardError, match="different checksum"):
            service.plan_upload_asset(
                "owner/repo",
                release_id=release.api_id,
                name=name,
                sha256="d" * 64,
                source_sha=authority.source_sha,
                actor_id="actor:test",
                correlation_id="corr:test",
            )
        with pytest.raises(GitHubStewardError, match="different candidate"):
            service.plan_upload_asset(
                "owner/repo",
                release_id=release.api_id,
                name="other.bin",
                sha256="a" * 64,
                source_sha="f" * 40,
                actor_id="actor:test",
                correlation_id="corr:test",
            )
        with pytest.raises(GitHubStewardError, match="finalize-before-campaign"):
            service.plan_finalize(
                "owner/repo",
                release_id=release.api_id,
                expected_head_sha=authority.source_sha,
                campaign_complete=False,
                actor_id="actor:test",
                correlation_id="corr:test",
            )
        with pytest.raises(GitHubStewardError, match="changed-head"):
            service.plan_finalize(
                "owner/repo",
                release_id=release.api_id,
                expected_head_sha="e" * 40,
                campaign_complete=True,
                actor_id="actor:test",
                correlation_id="corr:test",
            )


def test_acquired_remote_bytes_lifecycle_does_not_use_worktree(tmp_path):
    authority = resolve_release_version_authority(ROOT)
    dest = tmp_path / "bundle"
    paths = write_fixture_artifacts(
        dest,
        version=authority,
        desktop_executable=b"MZ-exe",
        desktop_installer=b"MZ-msi",
    )
    assets = {path.name: path.read_bytes() for path in paths.values()}
    acquired = write_acquired_assets(tmp_path / "acquired", assets)
    report = exercise_acquired_lifecycle(
        acquired, tmp_path / "work", expected_version=authority.bundle_version
    )
    assert report.worktree_bytes_used is False
    assert report.source == "REMOTE_DRAFT_BYTES"
    assert report.checks["uninstall"] == "PASS"
    assert report.checks["desktop_launch"] == "FIXTURE_BYTES_BOUND"
    worktree_like = tmp_path / "fake-worktree"
    write_acquired_assets(worktree_like, assets)
    (worktree_like / ".git").mkdir()
    (worktree_like / "src" / "project_pipeline").mkdir(parents=True)
    with pytest.raises(ValueError, match="worktree_bytes_used"):
        exercise_acquired_lifecycle(worktree_like, tmp_path / "work2")


def test_release_factory_cli_version(capsys):
    code = main(["release-factory", "version", "--root", str(ROOT)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version_authority"]["bundle_version"] == "0.9.0"


def test_live_draft_writes_require_approval_gate():
    args = Namespace(
        action="draft-apply",
        root=ROOT,
        provider="github",
        apply=True,
        approve=True,
        authorization_id="auth:test",
        profile="local",
        config_file=None,
        env_file=None,
        overrides=["security.external_writes_default=DENY"],
        output_dir=None,
        bundle_dir=None,
        desktop_dir=None,
        fixture_desktop=False,
        acquire_dir=None,
        work_dir=None,
        repository_slug=None,
        database=None,
        actor_id="actor:test",
        correlation_id="corr:test",
        campaign_complete=False,
        asset=None,
        release_id=None,
    )
    with pytest.raises(ConfigurationError, match="REQUIRE_APPROVAL"):
        _run_release_factory_command(args)
