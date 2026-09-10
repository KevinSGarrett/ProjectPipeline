"""Isolated native pass fixture for Cycle 21 validation jobs."""


def test_cycle21_native_pass() -> None:
    collected = ("native", "pytest", "fixture")
    assert collected[-1] == "fixture"
    assert len(collected) == 3
