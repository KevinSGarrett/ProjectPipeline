"""A failed provider dispatch must record why it failed, not only its kind.

Cycle 16-B lost a real four-hour qualification window to a
`cursor_cli_provider_dispatch` failure whose entire recorded evidence was the
opaque reason `process_error`. The adapter had the provider's own diagnostic
text in hand and discarded it, so the failure could not be classified as
transient or terminal from the preserved evidence.
"""

from __future__ import annotations

from typing import Any

from project_pipeline.agent_router.adapters import ProviderAdapterError
from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    _bounded_provider_detail,
)
from project_pipeline.autonomy_runtime.duration_probes import _dispatch_failure_detail


def _report(observations: dict[str, Any]) -> dict[str, Any]:
    return {"phases": [{"phase": "LIVE_DISPATCH", "observations": observations}]}


def test_provider_detail_is_preserved_bounded_and_single_line() -> None:
    error = ProviderAdapterError(
        "Cursor Agent CLI exited 1: upstream rate limit\nretry later",
        kind="PROCESS_ERROR",
    )

    detail = _bounded_provider_detail(error)

    assert "upstream rate limit" in detail
    assert "\n" not in detail
    assert len(detail) <= 280


def test_long_provider_detail_is_truncated() -> None:
    error = ProviderAdapterError("x" * 5000, kind="PROCESS_ERROR")

    assert len(_bounded_provider_detail(error)) == 280


def test_probe_surfaces_the_dispatch_failure_detail() -> None:
    report = _report({"error_kind": "PROCESS_ERROR", "error_detail": "exited 1: rate limited"})

    assert _dispatch_failure_detail(report) == "exited 1: rate limited"


def test_probe_reports_no_detail_when_dispatch_succeeded() -> None:
    report = _report({"provider_id": "provider:cursor-cli", "finish_reason": "completed"})

    assert _dispatch_failure_detail(report) is None
