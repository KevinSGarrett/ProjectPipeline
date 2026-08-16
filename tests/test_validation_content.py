from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_pipeline.io import iter_repository_files
from project_pipeline.validation.content import (
    check_forbidden_terminology,
    check_placeholders,
    check_secrets,
)
from project_pipeline.validation.models import ValidationReport
from project_pipeline.validation.registries import check_json_documents


class ContentValidationTests(unittest.TestCase):
    def test_forbidden_term_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = "wa" + "ve"
            (root / "sample.txt").write_text(f"one {token} here\n", encoding="utf-8")
            report = ValidationReport(str(root))
            policy = {"forbidden_term_parts": ["wa", "ve"], "forbidden_term_plural_suffix": "s"}
            check_forbidden_terminology(root, policy, report)
            self.assertEqual(len(report.errors), 1)

    def test_placeholder_and_secret_markers_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = "TO" + "DO"
            credential = "AK" + "IA" + "1234567890ABCDEF"
            (root / "bad.py").write_text(f"# {marker}\nvalue = '{credential}'\n", encoding="utf-8")
            report = ValidationReport(str(root))
            check_placeholders(root, report)
            check_secrets(root, report)
            self.assertGreaterEqual(len(report.errors), 2)

    def test_placeholder_exclusion_is_narrowly_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = "TO" + "DO"
            (root / "dummy").mkdir()
            (root / "src").mkdir()
            (root / "dummy" / "fixture.py").write_text(f"# {marker}\n", encoding="utf-8")
            (root / "src" / "production.py").write_text(f"# {marker}\n", encoding="utf-8")
            report = ValidationReport(str(root))
            check_placeholders(root, report, excluded_roots=("dummy",))
            self.assertEqual([item.path for item in report.errors], ["src/production.py"])

    def test_repository_iteration_excludes_local_agent_and_upstream_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                ".codex/state.json",
                ".codex_backups/backup.json",
                ".codex-session/state.json",
                ".codexfoo/state.json",
                ".local/state.db",
                "Github_Repo/upstream/source.py",
                "sample.egg-info/PKG-INFO",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("local-only\n", encoding="utf-8")
            (root / ".codex.json").write_text("local-only\n", encoding="utf-8")
            governed_skill = root / ".agents" / "skills" / "project" / "SKILL.md"
            governed_skill.parent.mkdir(parents=True)
            governed_skill.write_text("governed\n", encoding="utf-8")
            production = root / "src" / "production.py"
            production.parent.mkdir()
            production.write_text("value = 1\n", encoding="utf-8")

            observed = {path.relative_to(root).as_posix() for path in iter_repository_files(root)}
            self.assertEqual(
                observed,
                {".agents/skills/project/SKILL.md", "src/production.py"},
            )

    def test_secret_validation_does_not_read_local_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential = "AK" + "IA" + "1234567890ABCDEF"
            (root / ".env").write_text(f"VALUE={credential}\n", encoding="utf-8")
            report = ValidationReport(str(root))
            check_secrets(root, report)
            self.assertEqual(report.errors, [])

    def test_json_validation_excludes_untrusted_upstream_working_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = root / "Github_Repo" / "candidate" / "invalid.json"
            upstream.parent.mkdir(parents=True)
            upstream.write_text("{invalid\n", encoding="utf-8")
            governed = root / "config" / "valid.json"
            governed.parent.mkdir()
            governed.write_text('{"valid": true}\n', encoding="utf-8")
            report = ValidationReport(str(root))
            check_json_documents(root, report)
            self.assertEqual(report.errors, [])
