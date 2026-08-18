from src.app import build_message


def test_build_message() -> None:
    assert build_message() == "golden fixture ready"
