from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
collect_ignore = [
    "fixtures/cycle21_native_pass.py",
    "fixtures/cycle21_native_fail.py",
    "fixtures/cycle21_native_skip.py",
]


@pytest.fixture
def project_root() -> Path:
    return ROOT
