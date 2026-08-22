from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from project_pipeline.domain.base import DomainModel, utc_now


class RunbookStep(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    step_id: str = Field(min_length=2, max_length=200)
    action: str = Field(min_length=2, max_length=200)
    stop_on_failure: bool = True
    verification_required: bool = True


class ApprovedRunbook(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    runbook_id: str = Field(min_length=3, max_length=240)
    version: int = Field(ge=1)
    approved: bool
    approval_reference: str = Field(min_length=3, max_length=240)
    purpose: str = Field(min_length=3, max_length=1000)
    steps: tuple[RunbookStep, ...]

    @model_validator(mode="after")
    def validate_steps(self) -> ApprovedRunbook:
        if not self.steps:
            raise ValueError("runbook requires at least one step")
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError("runbook step identifiers must be unique")
        return self

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RunbookActionResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    step_id: str
    action: str
    success: bool
    verified: bool
    observation: str = Field(min_length=1, max_length=2000)


class RunbookExecutionResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    runbook_id: str
    runbook_version: int
    runbook_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    mode: Literal["DRY_RUN", "APPLY"]
    completed: bool
    stopped_at_step_id: str | None = None
    results: tuple[RunbookActionResult, ...]
    executed_at_utc: object = Field(default_factory=utc_now)


ActionHandler = Callable[[RunbookStep, dict[str, Any]], RunbookActionResult]
AuditSink = Callable[[dict[str, Any]], None]


def load_approved_runbook(path: Path) -> ApprovedRunbook:
    return ApprovedRunbook.model_validate_json(path.read_text(encoding="utf-8"))


class RunbookExecutor:
    """Execute only reviewed, versioned runbook steps with fail-closed verification.

    The executor never interprets free-form remediation text. Every action must be mapped to a
    pre-registered handler, every applied step is recorded, and a required verification failure
    stops execution before any later step can run.
    """

    def __init__(
        self, handlers: dict[str, ActionHandler], *, audit_sink: AuditSink | None = None
    ) -> None:
        self.handlers = dict(handlers)
        self.audit_sink = audit_sink

    def execute(
        self,
        runbook: ApprovedRunbook,
        *,
        context: dict[str, Any] | None = None,
        apply: bool = False,
    ) -> RunbookExecutionResult:
        if not runbook.approved:
            raise PermissionError("recovery automation requires an approved runbook")
        context = dict(context or {})
        mode: Literal["APPLY", "DRY_RUN"] = "APPLY" if apply else "DRY_RUN"
        results: list[RunbookActionResult] = []
        stopped: str | None = None
        for step in runbook.steps:
            if step.action not in self.handlers:
                result = RunbookActionResult(
                    step_id=step.step_id,
                    action=step.action,
                    success=False,
                    verified=False,
                    observation="action handler is not registered",
                )
            elif not apply:
                result = RunbookActionResult(
                    step_id=step.step_id,
                    action=step.action,
                    success=True,
                    verified=True,
                    observation="dry-run: approved action is registered; no mutation executed",
                )
            else:
                result = self.handlers[step.action](step, context)
                if result.step_id != step.step_id or result.action != step.action:
                    raise ValueError("runbook handler returned a result for the wrong step/action")
            results.append(result)
            self._record(runbook, mode, result)
            failed = (not result.success) or (step.verification_required and not result.verified)
            if failed and step.stop_on_failure:
                stopped = step.step_id
                break
        completed = (
            stopped is None
            and len(results) == len(runbook.steps)
            and all(r.success and r.verified for r in results)
        )
        return RunbookExecutionResult(
            runbook_id=runbook.runbook_id,
            runbook_version=runbook.version,
            runbook_fingerprint=runbook.fingerprint,
            mode=mode,
            completed=completed,
            stopped_at_step_id=stopped,
            results=tuple(results),
        )

    def _record(self, runbook: ApprovedRunbook, mode: str, result: RunbookActionResult) -> None:
        if self.audit_sink is None:
            return
        self.audit_sink(
            {
                "event_type": "RUNBOOK_STEP",
                "runbook_id": runbook.runbook_id,
                "runbook_version": runbook.version,
                "runbook_fingerprint": runbook.fingerprint,
                "mode": mode,
                "step_id": result.step_id,
                "action": result.action,
                "success": result.success,
                "verified": result.verified,
                "observation": result.observation,
            }
        )
