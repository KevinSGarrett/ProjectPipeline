
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CANDIDATE = Path(os.environ.get("PPQS_CANDIDATE_ROOT", ".")).resolve()
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "configurations"

class VisibleSchemaShiftContract(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(CANDIDATE)
        return subprocess.run([sys.executable, "-m", "schemashift", *args], text=True, capture_output=True, env=env)

    def test_validate_valid_v1(self):
        result = self.run_cli("validate", str(FIXTURES / "valid_v1.json"), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertTrue(body["valid"])

    def test_plan_v1_to_v3(self):
        result = self.run_cli("plan", str(FIXTURES / "valid_v1.json"), "--to", "3", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertEqual(body["path"], [1, 2, 3])

    def test_dry_run_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "config.json"
            target.write_bytes((FIXTURES / "valid_v1.json").read_bytes())
            before = target.read_bytes()
            result = self.run_cli("migrate", str(target), "--to", "3", "--dry-run", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), before)

if __name__ == "__main__":
    unittest.main()
