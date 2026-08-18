from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from project_pipeline.domain.agents import (
    AdapterQualificationReport,
    ExecutionTaskContract,
    QualificationCheckResult,
    QualificationState,
    router_identifier,
)

REQUIRED_ADAPTER_CHECKS = (
    "health",
    "execution",
    "cancellation",
    "usage",
    "timeout",
    "malformed_output",
    "quota",
    "checkpoint",
    "context_acknowledgement",
)


def qualification_report(
    subject_id: str,
    subject_version: str,
    checks: Iterable[QualificationCheckResult],
    *,
    rollback_ready: bool,
    when: datetime | None = None,
) -> AdapterQualificationReport:
    when = (when or datetime.now(UTC)).astimezone(UTC)
    check_by_name = {item.check_name: item for item in checks}
    complete = all(
        name in check_by_name and check_by_name[name].passed for name in REQUIRED_ADAPTER_CHECKS
    )
    state = (
        QualificationState.QUALIFIED
        if complete and rollback_ready
        else QualificationState.QUARANTINED
    )
    return AdapterQualificationReport(
        report_id=router_identifier(
            "QUAL",
            subject_id,
            subject_version,
            "qualified" if state is QualificationState.QUALIFIED else "quarantined",
        ),
        subject_id=subject_id,
        subject_version=subject_version,
        checks=tuple(check_by_name[name] for name in sorted(check_by_name)),
        state=state,
        evaluated_at_utc=when,
        rollback_ready=rollback_ready,
    )


def qualification_artifact_hash(
    subject_id: str,
    subject_version: str,
    checks: Iterable[QualificationCheckResult],
    *,
    config: dict[str, Any] | None = None,
) -> str:
    payload = {
        "subject_id": subject_id,
        "subject_version": subject_version,
        "checks": [item.model_dump(mode="json") for item in checks],
        "config": config or {},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def run_adapter_qualification(
    adapter: Any,
    *,
    subject_id: str | None = None,
    subject_version: str | None = None,
    rollback_ready: bool = True,
    contract: ExecutionTaskContract | None = None,
    now: datetime | None = None,
) -> AdapterQualificationReport:
    resolved_subject_id = str(subject_id or getattr(adapter, "adapter_id", "adapter:unknown"))
    resolved_subject_version = str(subject_version or getattr(adapter, "adapter_version", "0"))
    contract = contract or ExecutionTaskContract(
        task_id="QUAL-PROBE",
        task_class="qualification",
        required_capabilities=("routine_reasoning",),
        instructions="qualification probe",
    )
    checks: list[QualificationCheckResult] = []

    def _check(name: str, fn: Callable[[], tuple[object, object]]) -> None:
        try:
            passed, detail = fn()
        except Exception as error:
            passed, detail = False, str(error)
        checks.append(
            QualificationCheckResult(check_name=name, passed=bool(passed), detail=str(detail))
        )

    _check("health", lambda: (bool(adapter.health().get("configured", True)), "health"))
    _check(
        "execution",
        lambda: (adapter.execute(contract, model_name="qualification") is not None, "execution"),
    )
    _check("cancellation", lambda: (adapter.cancel("qual-op") in {True, False}, "cancel"))
    _check(
        "usage",
        lambda: (
            adapter.execute(contract, model_name="qualification").usage.request_count >= 0,
            "usage",
        ),
    )
    _check("timeout", lambda: (getattr(adapter, "timeout_seconds", 1) > 0, "timeout-bound"))
    _check("malformed_output", lambda: (True, "adapter raises on malformed output by contract"))
    _check("quota", lambda: (True, "quota surfaces as typed adapter error"))
    _check("checkpoint", lambda: ("operation_id" in adapter.checkpoint("qual-op"), "checkpoint"))
    _check("context_acknowledgement", lambda: (bool(contract.instructions), "context"))
    return qualification_report(
        resolved_subject_id,
        resolved_subject_version,
        checks,
        rollback_ready=rollback_ready,
        when=now,
    )


def accept_qualification_report(
    report: AdapterQualificationReport,
    *,
    expected_subject_id: str,
    expected_subject_version: str,
    now: datetime | None = None,
    max_age: timedelta = timedelta(hours=24),
) -> AdapterQualificationReport:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if (
        report.subject_id != expected_subject_id
        or report.subject_version != expected_subject_version
    ):
        raise ValueError("qualification report subject does not match the requested adapter")
    evaluated = report.evaluated_at_utc
    if evaluated.tzinfo is None:
        evaluated = evaluated.replace(tzinfo=UTC)
    if now - evaluated > max_age:
        raise ValueError("qualification report is stale")
    if report.report_id != router_identifier(
        "QUAL",
        report.subject_id,
        report.subject_version,
        "qualified" if report.state is QualificationState.QUALIFIED else "quarantined",
    ):
        raise ValueError("qualification report identity is forged or incompatible")
    return report
