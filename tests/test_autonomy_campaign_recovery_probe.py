from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_probe_module() -> ModuleType:
    script = Path(__file__).resolve().parents[1] / "scripts" / "autonomy_campaign_recovery_probe.py"
    spec = importlib.util.spec_from_file_location("autonomy_campaign_recovery_probe", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Cursor:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _Db:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def execute(self, *_args: object, **_kwargs: object) -> _Cursor:
        return _Cursor(self._row)


class _Controller:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._db = _Db(row)


def test_campaign_lock_live_returns_unavailable_sentinel_when_inspection_fails(
    monkeypatch,
) -> None:
    probe = _load_probe_module()
    monkeypatch.setattr(probe, "inspect_process", lambda _pid: None)

    observed = probe._campaign_lock_live(_Controller({"process_id": 4321}))

    assert observed == {"process_id": 4321, "alive": None, "inspection": "unavailable"}


def test_qualification_lock_live_returns_unavailable_sentinel_when_inspection_fails(
    monkeypatch,
) -> None:
    probe = _load_probe_module()
    monkeypatch.setattr(probe, "inspect_process", lambda _pid: None)

    observed = probe._qualification_owner_live(_Controller({"process_id": 8765}))

    assert observed == {"process_id": 8765, "alive": None, "inspection": "unavailable"}
