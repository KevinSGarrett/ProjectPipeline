from datetime import UTC, datetime, timedelta

from project_pipeline.agent_router import (
    normalize_circuit,
    record_failure,
    record_probe,
    record_success,
)
from project_pipeline.domain import CircuitBreakerPolicy, CircuitBreakerRecord, CircuitState


def test_circuit_opens_after_bounded_failures():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    policy = CircuitBreakerPolicy(failure_threshold=3, recovery_seconds=60)
    record = CircuitBreakerRecord(provider_id="provider:test", updated_at_utc=now)
    for i in range(3):
        record = record_failure(record, policy, now + timedelta(seconds=i), "timeout")
    assert record.state is CircuitState.OPEN and not record.permits(
        now + timedelta(seconds=10), policy
    )


def test_open_circuit_becomes_half_open_after_cooldown_and_probe_is_bounded():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    policy = CircuitBreakerPolicy(failure_threshold=1, recovery_seconds=30, half_open_probe_limit=1)
    record = record_failure(
        CircuitBreakerRecord(provider_id="provider:test", updated_at_utc=now),
        policy,
        now,
        "timeout",
    )
    record = normalize_circuit(record, policy, now + timedelta(seconds=31))
    assert record.state is CircuitState.HALF_OPEN and record.permits(
        now + timedelta(seconds=31), policy
    )
    record = record_probe(record, policy, now + timedelta(seconds=31))
    assert not record.permits(now + timedelta(seconds=31), policy)


def test_success_closes_circuit():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    policy = CircuitBreakerPolicy(failure_threshold=1)
    record = record_failure(
        CircuitBreakerRecord(provider_id="provider:test", updated_at_utc=now), policy, now, "x"
    )
    record = record_success(record, now + timedelta(seconds=1))
    assert record.state is CircuitState.CLOSED and record.consecutive_failures == 0
