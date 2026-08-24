from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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
    monkeypatch.setattr(module.shutil, "which", lambda _name: "npm")

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
