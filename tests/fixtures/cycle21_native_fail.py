"""Isolated native fail fixture. Must not be accepted as PASS."""


def test_cycle21_native_fail() -> None:
    raise AssertionError("known failing isolated fixture")
