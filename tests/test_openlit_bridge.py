from __future__ import annotations

from project_pipeline.observability.openlit import initialize_openlit, openlit_status


class FakeOpenLIT:
    def __init__(self):
        self.calls = []

    def init(self, **kwargs):
        self.calls.append(kwargs)


def test_openlit_bridge_reports_dependency_unavailable_without_claiming_activation() -> None:
    status = openlit_status(enabled=True)
    assert status.state in {"DEPENDENCY_UNAVAILABLE", "READY"}


def test_openlit_bridge_initializes_reviewed_sdk_through_optional_boundary() -> None:
    module = FakeOpenLIT()
    result = initialize_openlit(enabled=True, otlp_endpoint="http://127.0.0.1:4318", module=module)
    assert result["state"] == "INITIALIZED"
    assert module.calls == [{"otlp_endpoint": "http://127.0.0.1:4318"}]
    assert result["upstream_id"] == "UPSTREAM-077"
