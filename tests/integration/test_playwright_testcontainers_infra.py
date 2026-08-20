from __future__ import annotations

import importlib.util

from project_pipeline.verification.browser import playwright_runtime_status
from project_pipeline.verification.containers import docker_engine_ready


def test_playwright_status_does_not_invent_a_live_browser() -> None:
    status = playwright_runtime_status()
    package_present = importlib.util.find_spec("playwright") is not None
    assert status["package_present"] is package_present
    if package_present and status["chromium_present"]:
        assert status["status"] == "MEASURED"
    else:
        assert status["status"] == "UNAVAILABLE_IN_EXECUTION_ENVIRONMENT"
        assert status["reason"] in {
            "playwright_package_missing",
            "chromium_executable_missing",
        }


def test_testcontainers_python_package_is_optional_and_docker_probe_is_explicit() -> None:
    testcontainers_present = importlib.util.find_spec("testcontainers") is not None
    probe = docker_engine_ready()
    assert isinstance(testcontainers_present, bool)
    assert probe["ready"] in {True, False}
    if not probe["ready"]:
        assert probe["reason"] != "DOCKER_ENGINE_READY"
    if testcontainers_present:
        assert probe["ready"] is True or probe["reason"] != "DOCKER_CLI_MISSING"
