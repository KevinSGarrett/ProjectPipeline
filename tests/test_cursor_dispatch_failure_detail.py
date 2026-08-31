"""A failed provider dispatch must record why it failed, not only its kind.

Cycle 16-B lost a real four-hour qualification window to a
`cursor_cli_provider_dispatch` failure whose entire recorded evidence was the
opaque reason `process_error`. The adapter had the provider's own diagnostic
text in hand and discarded it at the boundary, so the failure could not be
classified as transient or terminal from the preserved evidence.

The excerpt is third-party stderr written into preserved evidence, so it must
also be redacted before it is stored.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from project_pipeline.agent_router.adapters import ProviderAdapterError
from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    DISPATCH_ERROR_DETAIL_KEY,
    QualificationPhase,
    _bounded_provider_detail,
    qualify_cursor_cli_provider,
)
from project_pipeline.autonomy_runtime.duration_probes import _dispatch_failure_detail

ROOT = Path(__file__).resolve().parents[1]


def _report(observations: dict[str, Any]) -> dict[str, Any]:
    return {
        "phases": [
            {
                "phase": QualificationPhase.LIVE_DISPATCH.value,
                "observations": observations,
            }
        ]
    }


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


def test_provider_detail_redacts_credential_material() -> None:
    """Provider stderr can echo credentials; evidence must never retain them."""

    error = ProviderAdapterError(
        "Cursor Agent CLI exited 1: rejected api_key=ghp_examplesecretvalue",
        kind="PROCESS_ERROR",
    )

    detail = _bounded_provider_detail(error)

    assert "ghp_examplesecretvalue" not in detail
    assert "REDACTED" in detail


def test_probe_surfaces_the_dispatch_failure_detail() -> None:
    report = _report(
        {"error_kind": "PROCESS_ERROR", DISPATCH_ERROR_DETAIL_KEY: "exited 1: rate limited"}
    )

    assert _dispatch_failure_detail(report) == "exited 1: rate limited"


def test_probe_reports_no_detail_when_dispatch_succeeded() -> None:
    report = _report({"provider_id": "provider:cursor-cli", "finish_reason": "completed"})

    assert _dispatch_failure_detail(report) is None


def test_qualification_emits_a_detail_the_probe_can_read(tmp_path: Path) -> None:
    """Bind producer to consumer through the real failure path.

    Asserting the key only against a hand-built dict would let the producer
    rename or relocate the observation while every test stayed green, silently
    restoring the opaque evidence this change exists to remove.
    """

    def failing_runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            returncode=1,
            stdout=b"",
            stderr=b"upstream refused the dispatch",
        )

    # The registered provider capability is discovered from the repository, so
    # the real tree is required to reach the dispatch phase at all.
    report = qualify_cursor_cli_provider(
        repository_root=ROOT,
        disposable_root=tmp_path / "disposable",
        runner=failing_runner,
        executable="cursor-agent",
    )

    assert report["outcome"] == "FAILED"
    assert report["live_dispatch"] is None
    detail = _dispatch_failure_detail(report)
    assert detail is not None
    assert "upstream refused the dispatch" in detail
