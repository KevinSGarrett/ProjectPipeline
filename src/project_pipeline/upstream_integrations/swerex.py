from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from project_pipeline.contracts.envelopes import ActionIntent
from project_pipeline.upstream_integrations.common import require_action_intent


class SwerexUnavailableError(RuntimeError):
    """Raised when the optional SWE-ReX package is not installed."""


@dataclass(frozen=True, slots=True)
class SwerexExecutionPlan:
    argv: tuple[str, ...]
    cwd: str
    timeout_seconds: float
    mutating: bool = False


class SwerexRuntimeAdapter:
    """Optional SWE-ReX bridge that keeps command execution infrastructure replaceable."""

    upstream_id = "UPSTREAM-102"

    def __init__(self, *, deployment_factory: Callable[[], Any] | None = None) -> None:
        self._deployment_factory = deployment_factory

    def available(self) -> bool:
        if self._deployment_factory is not None:
            return True
        try:
            import swerex  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return False
        return True

    def plan(
        self,
        root: Path,
        argv: tuple[str, ...],
        *,
        timeout_seconds: float = 300.0,
        mutating: bool = False,
    ) -> SwerexExecutionPlan:
        root = root.resolve()
        if not argv or any(not value or "\x00" in value for value in argv):
            raise ValueError("argv must contain non-empty values")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        return SwerexExecutionPlan(
            argv=argv, cwd=str(root), timeout_seconds=timeout_seconds, mutating=mutating
        )

    async def execute(
        self,
        plan: SwerexExecutionPlan,
        *,
        intent: ActionIntent | None = None,
    ) -> dict[str, object]:
        if plan.mutating:
            require_action_intent(
                intent,
                authority="execution.runtime",
                target=plan.cwd,
                operation="worker.execute",
            )
        if self._deployment_factory is None:
            try:
                from swerex.deployment.local import LocalDeployment  # type: ignore[import-not-found]  # noqa: I001
                from swerex.runtime.abstract import Command  # type: ignore[import-not-found]
            except ImportError as error:
                raise SwerexUnavailableError("swe-rex is not installed") from error
            deployment = LocalDeployment()
            command_factory: Callable[..., Any] = Command
        else:
            deployment = self._deployment_factory()
            candidate_factory = getattr(deployment, "command_factory", None)
            if callable(candidate_factory):
                command_factory = cast(Callable[..., Any], candidate_factory)
            else:

                def command_factory(**kwargs: Any) -> dict[str, Any]:
                    return kwargs

        await deployment.start()
        try:
            response = await deployment.runtime.execute(
                command_factory(
                    command=list(plan.argv),
                    timeout=plan.timeout_seconds,
                    shell=False,
                    check=False,
                    cwd=plan.cwd,
                )
            )
            payload: dict[str, object]
            if hasattr(response, "model_dump"):
                raw_payload: object = response.model_dump(mode="json")
                payload = (
                    dict(raw_payload)
                    if isinstance(raw_payload, dict)
                    else {"response": raw_payload}
                )
            elif isinstance(response, dict):
                payload = {str(key): value for key, value in response.items()}
            else:
                payload = {
                    "stdout": getattr(response, "stdout", ""),
                    "stderr": getattr(response, "stderr", ""),
                    "exit_code": getattr(response, "exit_code", None),
                }
            payload["upstream_id"] = self.upstream_id
            return payload
        finally:
            await deployment.stop()
