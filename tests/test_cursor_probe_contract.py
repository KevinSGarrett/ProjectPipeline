"""Contract tests for the cursor_cli_provider_dispatch duration probe.

These tests pin the qualification contract for the probe that repeatedly
disqualified Cycle 16-B campaigns. The defect was that the probe attempted a
live dispatch and then derived its verdict from *which* external failure mode
occurred: a dispatch that ran but left stray files in the disposable workspace
was relabelled NOT_APPLICABLE_PUBLIC_SOURCE and passed, while a PROCESS_ERROR
stayed FAILED and disqualified the campaign.

The accepted requirement REQ-PDEF-0011 forbids satisfying qualification with
mocks or simulation, and the Completion Gate requires a verified
qualified_real_worker_provider_dispatch stage. A not-applicable verdict
therefore must never stand in for that proof, and applicability must never be
decided by reinterpreting a failure after the fact.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from project_pipeline.autonomy_runtime import cursor_cli_qualification as cursor_cli_module
from project_pipeline.autonomy_runtime import duration_probes


def _probe(
    monkeypatch: pytest.MonkeyPatch, report: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """Run _probe_cursor against a stubbed provider qualification report."""

    def fake_qualify(**_kwargs: Any) -> dict[str, Any]:
        return report

    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.cursor_cli_qualification.qualify_cursor_cli_provider",
        fake_qualify,
    )
    return duration_probes._probe_cursor(tmp_path, tmp_path / "state")


def test_successful_live_dispatch_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    observations = _probe(
        monkeypatch,
        {
            "outcome": "PASSED",
            "provider_id": "cursor-cli",
            "live_dispatch": {"dispatch_id": "d-1", "ok": True},
            "replay_verified": True,
            "reasons": (),
        },
        tmp_path,
    )
    assert observations["outcome"] == "PASSED"
    assert observations["state"] is None
    assert observations["live_dispatch"] is not None


def test_out_of_scope_mutation_is_not_laundered_into_a_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dispatch that failed readback must not be relabelled not-applicable.

    This is the false-green path that let broken campaigns be admitted.
    """

    observations = _probe(
        monkeypatch,
        {
            "outcome": "FAILED",
            "provider_id": "cursor-cli",
            "live_dispatch": None,
            "replay_verified": False,
            "reasons": ("out-of-scope mutation",),
        },
        tmp_path,
    )
    assert observations["state"] != "NOT_APPLICABLE_PUBLIC_SOURCE"
    assert observations["outcome"] == "FAILED"


def test_process_error_is_reported_as_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observations = _probe(
        monkeypatch,
        {
            "outcome": "FAILED",
            "provider_id": "cursor-cli",
            "live_dispatch": None,
            "replay_verified": False,
            "reasons": ("process_error",),
        },
        tmp_path,
    )
    assert observations["outcome"] == "FAILED"
    assert observations["state"] != "NOT_APPLICABLE_PUBLIC_SOURCE"


def test_external_block_is_distinguishable_from_candidate_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Provider unavailability is an environment condition, not a candidate defect."""

    observations = _probe(
        monkeypatch,
        {
            "outcome": "BLOCKED_EXTERNAL",
            "provider_id": "cursor-cli",
            "live_dispatch": None,
            "replay_verified": False,
            "reasons": ("unavailable",),
        },
        tmp_path,
    )
    assert observations["outcome"] == "BLOCKED_EXTERNAL"
    assert observations["state"] != "NOT_APPLICABLE_PUBLIC_SOURCE"


def test_repeated_observations_of_the_same_report_are_identical(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same provider report must yield the same verdict on every recurrence.

    The campaign runs this probe on a four-hour cadence, so a verdict that
    varies between executions turns every long campaign into a coin flip.
    """

    report = {
        "outcome": "FAILED",
        "provider_id": "cursor-cli",
        "live_dispatch": None,
        "replay_verified": False,
        "reasons": ("out-of-scope mutation",),
    }
    first = _probe(monkeypatch, report, tmp_path)
    second = _probe(monkeypatch, report, tmp_path)
    assert first["state"] == second["state"]
    assert first["outcome"] == second["outcome"]


def test_not_applicable_never_counts_as_a_pass_for_this_probe() -> None:
    """Even if a not-applicable state is produced, it must not satisfy the probe.

    Contract B is authoritative: the Completion Gate requires a verified
    qualified_real_worker_provider_dispatch stage, so an absent dispatch cannot
    be a pass.
    """

    observations = {
        "outcome": "FAILED",
        "state": "NOT_APPLICABLE_PUBLIC_SOURCE",
        "live_dispatch": None,
    }
    assert not duration_probes._cursor_probe_ok(observations, identity_ok=True)


def test_duration_cursor_dispatch_pins_cheapest_model_not_auto() -> None:
    """Live duration dispatches must not use ``auto``; that selected high-cost models."""

    assert cursor_cli_module.DURATION_CURSOR_CLI_MODEL == "gpt-5.4-nano-none"
    assert cursor_cli_module.DURATION_CURSOR_CLI_MODEL != "auto"
    source = inspect.getsource(cursor_cli_module._dispatch_via_registered_adapter)
    assert "DURATION_CURSOR_CLI_MODEL" in source
    assert 'model_name="auto"' not in source
