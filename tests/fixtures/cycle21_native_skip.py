"""Isolated skip fixture. Mandatory skip must not PASS."""

import pytest


@pytest.mark.skip(reason="mandatory check skipped")
def test_cycle21_native_skip() -> None:
    collected = ("skipped", "mandatory")
    assert len(collected) == 2
