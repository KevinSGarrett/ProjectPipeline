from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

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
            "start",
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


def test_campaign_runner_rejects_a_database_other_than_the_runtime_binding(
    monkeypatch, tmp_path: Path
):
    module = _load_script()
    bound_database = tmp_path / "bound.sqlite3"
    bound_database.touch()
    monkeypatch.setattr(module, "apply_campaign_runtime_environment", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        module, "campaign_runtime_database_path", lambda _environment: bound_database
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_autonomy_campaign.py",
            "run",
            "--database",
            str(tmp_path / "other.sqlite3"),
            "--campaign-id",
            "QCAMP-C16B-TEST",
            "--runtime-environment-file",
            str(tmp_path / "campaign.runtime.env"),
        ],
    )

    with pytest.raises(SystemExit, match="must match the bound campaign runtime database"):
        module.main()


def test_campaign_run_fails_closed_without_cursor_api_key(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    bound_database = tmp_path / "bound.sqlite3"
    bound_database.touch()
    monkeypatch.setattr(module, "apply_campaign_runtime_environment", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        module, "campaign_runtime_database_path", lambda _environment: bound_database
    )
    monkeypatch.setattr(
        module,
        "limited_campaign_subprocess_environment",
        lambda *_args, **_kwargs: {"PATH": "safe-path"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_autonomy_campaign.py",
            "run",
            "--database",
            str(bound_database),
            "--campaign-id",
            "QCAMP-C16B-TEST",
            "--runtime-environment-file",
            str(tmp_path / "campaign.runtime.env"),
        ],
    )

    with pytest.raises(SystemExit, match="CURSOR_API_KEY"):
        module.main()
