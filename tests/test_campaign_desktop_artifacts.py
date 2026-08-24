from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "campaign_desktop_artifact_builder",
        ROOT / "scripts" / "build_campaign_desktop_artifacts.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_desktop_builder_stages_candidate_bound_native_artifacts(tmp_path, monkeypatch):
    module = _load_builder()
    root = tmp_path / "candidate"
    frontend = root / "apps" / "command_center"
    frontend.mkdir(parents=True)
    (frontend / "package-lock.json").write_text("{}\n", encoding="utf-8")
    output = tmp_path / "desktop-artifacts"
    sha = "a" * 40
    tree = "b" * 40
    monkeypatch.setattr(
        module,
        "inspect_worktree_identity",
        lambda _root: {"ok": True, "dirty": False, "sha": sha, "tree": tree},
    )
    monkeypatch.setattr(module.shutil, "which", lambda _name, path=None: "npm")

    def fake_run(command, *, cwd, environment):
        assert cwd == frontend
        if "tauri:build" in command:
            release = Path(environment["CARGO_TARGET_DIR"]) / "release"
            (release / "bundle" / "nsis").mkdir(parents=True)
            (release / "project-pipeline-command-center.exe").write_bytes(b"MZ-native")
            (release / "bundle" / "nsis" / "ProjectPipeline-setup.exe").write_bytes(b"MZ-installer")

    monkeypatch.setattr(module, "_run", fake_run)
    result = module.build_artifacts(
        root=root,
        output_dir=output,
        expected_sha=sha,
        expected_tree=tree,
    )

    assert result["state"] == "BUILT"
    for kind, item in result["artifacts"].items():
        path = output / item["name"]
        assert path.is_file()
        sidecar = json.loads(path.with_suffix(path.suffix + ".candidate.json").read_text())
        assert sidecar["kind"] == kind
        assert sidecar["source_sha"] == sha
        assert sidecar["source_tree"] == tree


def test_campaign_desktop_builder_rejects_preseeded_output(tmp_path, monkeypatch):
    module = _load_builder()
    root = tmp_path / "candidate"
    root.mkdir()
    output = tmp_path / "desktop-artifacts"
    output.mkdir()
    (output / "desktop_build.json").write_text("{}\n", encoding="utf-8")
    sha = "a" * 40
    tree = "b" * 40
    monkeypatch.setattr(
        module,
        "inspect_worktree_identity",
        lambda _root: {"ok": True, "dirty": False, "sha": sha, "tree": tree},
    )
    with pytest.raises(RuntimeError, match="desktop-build-output-conflict"):
        module.build_artifacts(
            root=root,
            output_dir=output,
            expected_sha=sha,
            expected_tree=tree,
        )


def test_campaign_desktop_builder_stages_gnu_target_artifacts(tmp_path, monkeypatch):
    module = _load_builder()
    root = tmp_path / "candidate"
    frontend = root / "apps" / "command_center"
    frontend.mkdir(parents=True)
    (frontend / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (root / "rust-toolchain.toml").write_text(
        "[toolchain]\nchannel = \"1.97.1\"\n", encoding="utf-8"
    )
    output = tmp_path / "desktop-artifacts"
    sha = "a" * 40
    tree = "b" * 40
    monkeypatch.setattr(
        module,
        "inspect_worktree_identity",
        lambda _root: {"ok": True, "dirty": False, "sha": sha, "tree": tree},
    )
    monkeypatch.setattr(module.shutil, "which", lambda _name, path=None: "npm")
    monkeypatch.setattr(
        module,
        "_prepare_native_build_environment",
        lambda environment: (
            {**environment, "CARGO_BUILD_TARGET": module._GNU_TARGET},
            module._GNU_TARGET,
            "x86_64-w64-mingw32-gcc.exe",
        ),
    )

    def fake_run(command, *, cwd, environment):
        assert cwd == frontend
        if "tauri:build" in command:
            assert command == [
                "npm",
                "run",
                "tauri:build",
                "--",
                "--target",
                module._GNU_TARGET,
                "--",
                "--locked",
            ]
            assert environment["RUSTUP_TOOLCHAIN"] == "1.97.1-x86_64-pc-windows-gnu"
            release = Path(environment["CARGO_TARGET_DIR"]) / module._GNU_TARGET / "release"
            (release / "bundle" / "nsis").mkdir(parents=True)
            (release / "project-pipeline-command-center.exe").write_bytes(b"MZ-native")
            (release / "bundle" / "nsis" / "ProjectPipeline-setup.exe").write_bytes(b"MZ-installer")

    monkeypatch.setattr(module, "_run", fake_run)
    result = module.build_artifacts(
        root=root,
        output_dir=output,
        expected_sha=sha,
        expected_tree=tree,
    )

    assert result["build_target"] == module._GNU_TARGET
    assert result["compiler"] == "x86_64-w64-mingw32-gcc.exe"
    assert result["rust_toolchain"] == "1.97.1-x86_64-pc-windows-gnu"
    assert (output / "project-pipeline-command-center.exe").is_file()


def test_campaign_desktop_builder_discovers_winget_winlibs(tmp_path, monkeypatch):
    module = _load_builder()
    winlibs_bin = (
        tmp_path
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "BrechtSanders.WinLibs.POSIX.UCRT_example"
        / "mingw64"
        / "bin"
    )
    winlibs_bin.mkdir(parents=True)
    (winlibs_bin / module._GNU_GCC).write_bytes(b"")
    monkeypatch.setattr(module.shutil, "which", lambda _name, path=None: None)

    environment, target, compiler = module._prepare_native_build_environment(
        {"LOCALAPPDATA": str(tmp_path), "PATH": "base-path"}
    )

    assert target == module._GNU_TARGET
    assert environment["CARGO_BUILD_TARGET"] == module._GNU_TARGET
    assert environment["PATH"].startswith(str(winlibs_bin))
    assert compiler == str(winlibs_bin / module._GNU_GCC)
