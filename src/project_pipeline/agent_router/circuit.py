from __future__ import annotations

from datetime import UTC, datetime

from project_pipeline.domain.agents import (
    CircuitBreakerPolicy,
    CircuitBreakerRecord,
    CircuitState,
)


def normalize_circuit(
    record: CircuitBreakerRecord, policy: CircuitBreakerPolicy, when: datetime
) -> CircuitBreakerRecord:
    when = when.astimezone(UTC)
    if record.state is CircuitState.OPEN and record.permits(when, policy):
        return record.model_copy(
            update={"state": CircuitState.HALF_OPEN, "half_open_probes": 0, "updated_at_utc": when}
        )
    return record


def record_failure(
    record: CircuitBreakerRecord, policy: CircuitBreakerPolicy, when: datetime, reason: str
) -> CircuitBreakerRecord:
    when = when.astimezone(UTC)
    record = normalize_circuit(record, policy, when)
    failures = record.consecutive_failures + 1
    if record.state is CircuitState.HALF_OPEN or failures >= policy.failure_threshold:
        return record.model_copy(
            update={
                "state": CircuitState.OPEN,
                "consecutive_failures": failures,
                "opened_at_utc": when,
                "half_open_probes": 0,
                "last_failure": reason,
                "updated_at_utc": when,
            }
        )
    return record.model_copy(
        update={"consecutive_failures": failures, "last_failure": reason, "updated_at_utc": when}
    )


def record_success(record: CircuitBreakerRecord, when: datetime) -> CircuitBreakerRecord:
    when = when.astimezone(UTC)
    return record.model_copy(
        update={
            "state": CircuitState.CLOSED,
            "consecutive_failures": 0,
            "opened_at_utc": None,
            "half_open_probes": 0,
            "last_failure": None,
            "updated_at_utc": when,
        }
    )


def record_probe(
    record: CircuitBreakerRecord, policy: CircuitBreakerPolicy, when: datetime
) -> CircuitBreakerRecord:
    when = when.astimezone(UTC)
    record = normalize_circuit(record, policy, when)
    if (
        record.state is not CircuitState.HALF_OPEN
        or record.half_open_probes >= policy.half_open_probe_limit
    ):
        return record
    return record.model_copy(
        update={"half_open_probes": record.half_open_probes + 1, "updated_at_utc": when}
    )
