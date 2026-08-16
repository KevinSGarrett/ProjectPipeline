from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from project_pipeline.domain.agents import (
    AdapterQualificationReport,
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
