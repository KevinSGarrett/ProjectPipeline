
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CANDIDATE = Path(os.environ.get("PPQS_CANDIDATE_ROOT", ".")).resolve()
DATA = Path(__file__).resolve().parents[1] / "data" / "visible"

class VisibleDemandForgeContract(unittest.TestCase):
    def run_cli(self, *args):
        env=os.environ.copy(); env["PYTHONPATH"] = str(CANDIDATE)
        return subprocess.run([sys.executable, "-m", "demandforge", *map(str,args)], text=True, capture_output=True, env=env)

    def test_train_and_forecast_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            model=Path(td)/"model.json"; output=Path(td)/"forecast.csv"
            result=self.run_cli("train", DATA/"training.csv", "--model-out", model)
            self.assertEqual(result.returncode,0,result.stderr); self.assertTrue(model.exists())
            result=self.run_cli("forecast", "--model", model, "--history", DATA/"training.csv", "--horizon", 7, "--out", output)
            self.assertEqual(result.returncode,0,result.stderr); self.assertTrue(output.exists())
            rows=list(csv.DictReader(output.open()))
            self.assertGreater(len(rows),0); self.assertIn("lower",rows[0]); self.assertIn("upper",rows[0])

if __name__ == "__main__": unittest.main()
