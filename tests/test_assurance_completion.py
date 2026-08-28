"""Public-safe Completion Gate and publication-gate coverage.

Publication must remain impossible until the deterministic Completion Gate
independently declares completion. These tests pin that boundary so a future
change cannot quietly make the pre-admission gate sufficient for release.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_pipeline.release_hardening.pre_admission import (
    REQUIRED_DURATION_STAGES,
    SELF_CERTIFICATION_BOUNDARY_BLOCKER,
    evaluate_final_publication_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

ALL_STAGES_COMPLETE = dict.fromkeys(REQUIRED_DURATION_STAGES, True)


def test_publication_blocked_without_any_duration_evidence() -> None:
    verdict = evaluate_final_publication_gate(
        REPO_ROOT,
        duration_evidence={},
        completion_gate_complete=False,
        published_bytes_verified=False,
    )
    assert verdict.eligible is False
    for stage in REQUIRED_DURATION_STAGES:
        assert any(stage in blocker for blocker in verdict.blockers)


@pytest.mark.parametrize("missing", REQUIRED_DURATION_STAGES)
def test_publication_blocked_when_any_single_stage_is_missing(missing: str) -> None:
    evidence = dict(ALL_STAGES_COMPLETE)
    evidence[missing] = False
    verdict = evaluate_final_publication_gate(
        REPO_ROOT,
        duration_evidence=evidence,
        completion_gate_complete=True,
        published_bytes_verified=True,
    )
    assert verdict.eligible is False
    assert any(missing in blocker for blocker in verdict.blockers)


def test_publication_blocked_when_completion_gate_is_incomplete() -> None:
    verdict = evaluate_final_publication_gate(
        REPO_ROOT,
        duration_evidence=ALL_STAGES_COMPLETE,
        completion_gate_complete=False,
        published_bytes_verified=True,
    )
    assert verdict.eligible is False
    assert SELF_CERTIFICATION_BOUNDARY_BLOCKER in verdict.blockers


def test_publication_blocked_without_published_byte_verification() -> None:
    verdict = evaluate_final_publication_gate(
        REPO_ROOT,
        duration_evidence=ALL_STAGES_COMPLETE,
        completion_gate_complete=True,
        published_bytes_verified=False,
    )
    assert verdict.eligible is False
    assert any("published-byte" in blocker for blocker in verdict.blockers)


def test_pre_admission_alone_never_authorizes_publication() -> None:
    verdict = evaluate_final_publication_gate(
        REPO_ROOT,
        duration_evidence={},
        completion_gate_complete=False,
        published_bytes_verified=False,
    )
    assert verdict.eligible is False


def test_completion_gate_evaluator_is_not_bypassed() -> None:
    """The publication gate must consume a Completion Gate verdict, not infer one."""

    import inspect

    from project_pipeline.release_hardening import pre_admission

    signature = inspect.signature(pre_admission.evaluate_final_publication_gate)
    assert "completion_gate_complete" in signature.parameters
    source = inspect.getsource(pre_admission.evaluate_final_publication_gate)
    assert "completion_gate_complete" in source
    # Eligibility must be conjunctive over blockers, never a default True.
    assert "not blockers" in source


def test_required_duration_stages_are_the_real_ladder() -> None:
    assert REQUIRED_DURATION_STAGES == (
        "UNATTENDED_4_HOUR",
        "UNATTENDED_24_HOUR",
        "UNATTENDED_72_HOUR",
    )
