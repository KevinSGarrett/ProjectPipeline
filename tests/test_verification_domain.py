from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from project_pipeline.domain.verification import (
    ToolActivationState,
    VerificationCategory,
    VerificationCheckResult,
    VerificationCheckSpec,
    VerificationResultState,
    VerificationRun,
    VerificationToolActivation,
    verification_fingerprint,
    verification_identifier,
)


def test_verification_identifier_is_deterministic():
    assert verification_identifier("VRUN", "a", "b") == verification_identifier("VRUN", "a", "b")


def test_check_spec_identity_is_semantic():
    name = "contract"
    category = VerificationCategory.CONTRACT
    description = "contract verification"
    value = VerificationCheckSpec(
        check_id=verification_identifier("VCHK", name, category.value, "True", description),
        name=name,
        category=category,
        description=description,
    )
    assert value.required


def test_required_check_cannot_be_silently_skipped():
    with pytest.raises(ValidationError):
        VerificationCheckResult(
            check_id="VCHK-" + "A" * 20,
            state=VerificationResultState.SKIPPED,
            required=True,
            category=VerificationCategory.CONTRACT,
            duration_ms=0,
            reason="skip",
        )


def test_verification_run_recomputes_required_failure_counts():
    result = VerificationCheckResult(
        check_id="VCHK-" + "A" * 20,
        state=VerificationResultState.PASS,
        required=True,
        category=VerificationCategory.CONTRACT,
        duration_ms=1,
        reason="pass",
    )
    now = datetime.now(UTC)
    run = VerificationRun(
        run_id=verification_identifier("VRUN", "project", "profile", "source"),
        project_id="PROJECT-PIPELINE",
        profile="test",
        source_fingerprint=verification_fingerprint("source"),
        results=(result,),
        final_state=VerificationResultState.PASS,
        required_fail_count=0,
        required_blocked_count=0,
        optional_skipped_count=0,
        started_at_utc=now,
        completed_at_utc=now,
    )
    assert run.final_state is VerificationResultState.PASS


def test_executed_tool_requires_evidence_and_paths():
    with pytest.raises(ValidationError):
        VerificationToolActivation(
            activation_id=verification_identifier("VTOOL", "UPSTREAM-063", "EXECUTED"),
            upstream_id="UPSTREAM-063",
            repository="microsoft/playwright",
            state=ToolActivationState.EXECUTED,
            integration_paths=("src/project_pipeline/verification/browser.py",),
            evidence_paths=(),
            activation_phase="PASS16",
            reason="executed",
        )
