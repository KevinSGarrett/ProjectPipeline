from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from project_pipeline.archive import create_archive, verify_archive


class ArchiveTests(unittest.TestCase):
    def test_archive_is_deterministic_and_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "ExampleProject"
            root.mkdir()
            (root / "README.md").write_text("# Example\n", encoding="utf-8")
            first = create_archive(root, base / "first.zip")
            second = create_archive(root, base / "second.zip")
            first_hash = hashlib.sha256(first.read_bytes()).hexdigest()
            second_hash = hashlib.sha256(second.read_bytes()).hexdigest()
            self.assertEqual(first_hash, second_hash)
            report = verify_archive(first, "ExampleProject")
            self.assertEqual(report.errors, [])
            self.assertEqual(report.file_count, 1)

    def test_wrong_root_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "Actual"
            root.mkdir()
            (root / "x.txt").write_text("x", encoding="utf-8")
            archive = create_archive(root, base / "archive.zip")
            report = verify_archive(archive, "Expected")
            self.assertNotEqual(report.errors, [])
