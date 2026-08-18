from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from project_pipeline.io import sha256_canonical_file
from project_pipeline.validation import RepositoryValidator

ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_repository_contract_has_no_errors(self) -> None:
        report = RepositoryValidator(ROOT).validate()
        self.assertEqual([], [item.as_dict() for item in report.errors], report.render())

    def test_canonical_text_digest_ignores_working_tree_crlf(self) -> None:
        from tempfile import TemporaryDirectory

        from project_pipeline.io import sha256_canonical_file, sha256_file

        with TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_bytes(b'{"ok": true}\r\n')
            lf_digest = hashlib.sha256(b'{"ok": true}\n').hexdigest()
            self.assertEqual(sha256_canonical_file(path), lf_digest)
            self.assertNotEqual(sha256_file(path), lf_digest)

    def test_live_qualification_evidence_digest_binds_git_canonical_lf(self) -> None:
        artifact = (
            ROOT / "evidence/autonomy_runtime/live_qualification/live_qualification_latest.json"
        )
        ledger_rows = [
            json.loads(line)
            for line in (ROOT / "evidence/EVIDENCE_LEDGER.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        record = next(row for row in ledger_rows if row["evidence_id"] == "EVID-000178")
        raw = artifact.read_bytes()
        lf = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        self.assertEqual(record["sha256"], hashlib.sha256(lf).hexdigest())
        self.assertEqual(record["sha256"], sha256_canonical_file(artifact))
        self.assertEqual(record["artifact_path"], artifact.relative_to(ROOT).as_posix())
