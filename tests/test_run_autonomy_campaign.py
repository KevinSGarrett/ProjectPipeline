from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "run_autonomy_campaign_script", ROOT / "scripts" / "run_autonomy_campaign.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_runner_returns_structured_host_safety_block(monkeypatch, capsys, tmp_path: Path):
    module = _load_script()
    monkeypatch.setattr(
        module,
        "evaluate_local_host_safety",
        lambda _root: {"state": "BLOCKED", "blockers": [{"code": "recent-nvme-reset"}]},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_autonomy_campaign.py",
            "run",
            "--database",
            str(tmp_path / "campaign.sqlite3"),
            "--campaign-id",
            "CAMPAIGN-test",
        ],
    )

    assert module.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["campaign"] == {"state": "BLOCKED", "reason": "host-safety-blocked"}
    assert payload["host_safety"]["blockers"] == [{"code": "recent-nvme-reset"}]
