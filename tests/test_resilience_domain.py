import pytest

from project_pipeline.domain.resilience import (
    LocalRuntimeSpec,
    RecoveryObjective,
    RestoreState,
    RestoreVerification,
    RuntimeKind,
    resilience_identifier,
)


def test_recovery_objective_requires_positive_rto():
    with pytest.raises(ValueError):
        RecoveryObjective(
            objective_id=resilience_identifier("RPO", "bad"),
            domain="bad",
            rpo_seconds=0,
            rto_seconds=0,
            backup_strategy="safe backup",
            destructive_restore_interval_days=30,
            rationale="test",
        )


def test_local_runtime_is_advisory_only():
    r = LocalRuntimeSpec(
        runtime_id=resilience_identifier("RUNTIME", "ollama"),
        kind=RuntimeKind.OLLAMA,
        endpoint="http://127.0.0.1:11434",
        capabilities=("summarization",),
    )
    assert r.advisory_only is True


def test_restore_verification_requires_checks():
    with pytest.raises(ValueError):
        RestoreVerification(
            restore_id=resilience_identifier("RESTORE", "x"),
            backup_id="b",
            isolated_environment="test",
            state=RestoreState.VERIFIED,
            checks=(),
        )
