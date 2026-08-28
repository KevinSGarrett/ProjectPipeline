"""The qualification report must surface the dispatch it actually performed.

The duration probe gates on `live_dispatch` to prove a real bound provider
dispatch occurred, per REQ-PDEF-0011 and the Completion Gate's
qualified_real_worker_provider_dispatch stage. The report never populated that
field, so it was always null and the gate could never be satisfied by any
outcome, including a genuinely successful dispatch.
"""

from __future__ import annotations

from typing import Any

from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    PROVIDER_ID,
    QualificationPhase,
    _finish,
)


def _phases(
    *, dispatch: dict[str, Any] | None = None, replay_ok: bool | None = None
) -> list[dict[str, Any]]:
    phases: list[dict[str, Any]] = []
    if dispatch is not None:
        phases.append({"phase": QualificationPhase.LIVE_DISPATCH.value, "observations": dispatch})
    if replay_ok is not None:
        phases.append({"phase": QualificationPhase.REPLAY.value, "observations": {"ok": replay_ok}})
    return phases


def test_successful_dispatch_is_surfaced_on_the_report(tmp_path) -> None:
    dispatch = {"provider_id": PROVIDER_ID, "exit_code": 0, "dispatch_id": "d-1"}

    report = _finish(
        "PASSED",
        _phases(dispatch=dispatch, replay_ok=True),
        tmp_path / "missing-workspace",
        None,
        reasons=(),
    )

    assert report["live_dispatch"] == dispatch
    assert report["replay_verified"] is True


def test_report_without_a_dispatch_phase_has_no_live_dispatch(tmp_path) -> None:
    report = _finish(
        "FAILED",
        _phases(),
        tmp_path / "missing-workspace",
        None,
        reasons=("unavailable",),
    )

    assert report["live_dispatch"] is None
    assert report["replay_verified"] is None


def test_blocked_dispatch_phase_does_not_count_as_a_dispatch(tmp_path) -> None:
    """A phase recording only an error must not be mistaken for a real dispatch."""

    report = _finish(
        "BLOCKED_EXTERNAL",
        _phases(dispatch={"error_kind": "UNAVAILABLE", "provider_state": "absent"}),
        tmp_path / "missing-workspace",
        None,
        reasons=("unavailable",),
    )

    assert report["live_dispatch"] is None


def test_failed_replay_is_surfaced_as_unverified(tmp_path) -> None:
    report = _finish(
        "FAILED",
        _phases(dispatch={"provider_id": PROVIDER_ID}, replay_ok=False),
        tmp_path / "missing-workspace",
        None,
        reasons=("conflicting replay",),
    )

    assert report["live_dispatch"] == {"provider_id": PROVIDER_ID}
    assert report["replay_verified"] is False
