from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_pipeline.manifest import build_manifest, verify_manifest, write_manifest


class ManifestTests(unittest.TestCase):
    def test_manifest_is_sorted_and_detects_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Example"
            root.mkdir()
            (root / "b.txt").write_text("b\n", encoding="utf-8")
            (root / "a.txt").write_text("a\n", encoding="utf-8")
            manifest = write_manifest(root)
            self.assertEqual([item["path"] for item in manifest["files"]], ["a.txt", "b.txt"])
            self.assertEqual(verify_manifest(root), [])
            (root / "a.txt").write_text("changed\n", encoding="utf-8")
            self.assertNotEqual(verify_manifest(root), [])

    def test_manifest_aggregate_is_stable_for_same_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_text("same\n", encoding="utf-8")
            first = build_manifest(root)["aggregate_sha256"]
            second = build_manifest(root)["aggregate_sha256"]
            self.assertEqual(first, second)

    def test_manifest_root_name_uses_canonical_project_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            names = []
            for checkout_name in ("Project_X", "pp-task-000327"):
                root = parent / checkout_name
                (root / "config").mkdir(parents=True)
                (root / "config/project.json").write_text(
                    json.dumps({"target_local_root": r"C:\Project_X"}), encoding="utf-8"
                )
                names.append(build_manifest(root)["root_name"])
            self.assertEqual(names, ["Project_X", "Project_X"])

    def test_manifest_verification_detects_root_name_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_text("same\n", encoding="utf-8")
            write_manifest(root)
            manifest_path = root / "PROJECT_MANIFEST.json"
            recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
            recorded["root_name"] = "different-checkout"
            manifest_path.write_text(json.dumps(recorded), encoding="utf-8")
            self.assertIn("Manifest root name mismatch", verify_manifest(root))

    def test_manifest_text_digests_are_line_ending_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "data.txt"
            path.write_bytes(b"first\nsecond\n")
            lf_record = build_manifest(root)["files"][0]
            path.write_bytes(b"first\r\nsecond\r\n")
            crlf_record = build_manifest(root)["files"][0]
            self.assertEqual(lf_record["sha256"], crlf_record["sha256"])
            self.assertEqual(lf_record["size_bytes"], crlf_record["size_bytes"])

    def test_manifest_excludes_local_secrets_and_internal_working_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                ".env",
                ".env.local",
                "private.key",
                ".codex/session.json",
                ".codex_backups/backup.json",
                ".codexfoo/state.json",
                ".local/state.db",
                ".coverage",
                ".coverage.worker-1",
                "coverage.xml",
                "junit-results.xml",
                "build/generated.py",
                "dist/project.whl",
                "htmlcov/index.html",
                "Github_Repo/upstream/source.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("local-only\n", encoding="utf-8")
            (root / ".git").write_text("gitdir: ../worktrees/example\n", encoding="utf-8")
            (root / ".codex.json").write_text("local-only\n", encoding="utf-8")
            for relative in (".env.example", ".agents/skills/project/SKILL.md", "src/app.py"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("public\n", encoding="utf-8")

            paths = {item["path"] for item in build_manifest(root)["files"]}
            self.assertEqual(
                paths,
                {".agents/skills/project/SKILL.md", ".env.example", "src/app.py"},
            )

    def test_manifest_tracks_shared_cursor_controls_but_excludes_private_cursor_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                ".cursor/rules/authority.mdc",
                ".cursor/cli.json",
                ".cursor/hooks.json",
                ".cursor/hooks/guard_shell.py",
                ".cursor/mcp.example.json",
                ".cursor/mcp.json",
                ".cursor/scratchpad.md",
                ".cursor/session.log",
                ".cursor/private/secret-notes.txt",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("value\n", encoding="utf-8")
            paths = {item["path"] for item in build_manifest(root)["files"]}
            self.assertEqual(
                paths,
                {
                    ".cursor/cli.json",
                    ".cursor/hooks.json",
                    ".cursor/hooks/guard_shell.py",
                    ".cursor/mcp.example.json",
                    ".cursor/rules/authority.mdc",
                },
            )
