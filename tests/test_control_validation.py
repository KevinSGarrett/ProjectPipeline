from __future__ import annotations

from pathlib import Path

from project_pipeline.control import validate_control_foundation

ROOT = Path(__file__).resolve().parents[1]


def test_control_foundation_is_registered_and_migrated() -> None:
    assert validate_control_foundation(ROOT) == []
