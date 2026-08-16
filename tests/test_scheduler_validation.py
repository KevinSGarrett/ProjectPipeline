from pathlib import Path

from project_pipeline.scheduler import validate_scheduler_foundation

ROOT = Path(__file__).resolve().parents[1]


def test_scheduler_foundation_is_registered() -> None:
    assert validate_scheduler_foundation(ROOT) == []
