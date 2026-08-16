from python.worker import run


def test_run() -> None:
    assert run() == "ok"
