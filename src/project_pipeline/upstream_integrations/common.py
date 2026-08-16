from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from project_pipeline.contracts.envelopes import ActionIntent, ApprovalState


class UpstreamIntegrationError(RuntimeError):
    """Raised when an upstream adapter cannot safely plan or execute an operation."""


Runner = Callable[
    [Sequence[str], Path, str | None, float, Mapping[str, str] | None],
    subprocess.CompletedProcess[str],
]


def default_runner(
    argv: Sequence[str],
    cwd: Path,
    stdin: str | None,
    timeout: float,
    env: Mapping[str, str] | None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
        env=None if env is None else dict(env),
    )


@dataclass(frozen=True, slots=True)
class CommandPlan:
    upstream_id: str
    argv: tuple[str, ...]
    cwd: str
    mutating: bool = False
    network_required: bool = False
    stdin: str | None = None
    output_format: str = "text"
    evidence_sources: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def redacted(self) -> dict[str, object]:
        return {
            "upstream_id": self.upstream_id,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "mutating": self.mutating,
            "network_required": self.network_required,
            "output_format": self.output_format,
            "evidence_sources": list(self.evidence_sources),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    state: str
    returncode: int
    stdout: str
    stderr: str
    parsed: object | None = None


def executable_available(executable: str) -> bool:
    return shutil.which(executable) is not None


def confined(root: Path, path: Path, *, must_exist: bool = False) -> Path:
    root = root.resolve()
    candidate = path if path.is_absolute() else root / path
    candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path escapes governed root: {path}") from error
    if must_exist and not candidate.exists():
        raise ValueError(f"path does not exist: {candidate}")
    return candidate


def require_safe_value(value: str, *, field_name: str) -> str:
    if not value or value.startswith("-") or "\x00" in value:
        raise ValueError(f"{field_name} must be a non-option value")
    return value


def require_action_intent(
    intent: ActionIntent | None,
    *,
    authority: str,
    target: str,
    operation: str,
) -> None:
    if intent is None or intent.approval_state is not ApprovalState.APPROVED:
        raise UpstreamIntegrationError("approved action intent is required")
    if intent.authority != authority or intent.target != target or intent.operation != operation:
        raise UpstreamIntegrationError("action intent does not authorize this operation")


def execute_plan(
    plan: CommandPlan,
    *,
    runner: Runner = default_runner,
    timeout_seconds: float = 300.0,
    allow_network: bool = False,
    intent: ActionIntent | None = None,
    authority: str = "execution.runtime",
    operation: str = "worker.execute",
    env: Mapping[str, str] | None = None,
) -> CommandOutcome:
    if plan.network_required and not allow_network:
        raise UpstreamIntegrationError(
            "network-enabled upstream execution requires explicit allowance"
        )
    if plan.mutating:
        require_action_intent(
            intent,
            authority=authority,
            target=plan.cwd,
            operation=operation,
        )
    result = runner(plan.argv, Path(plan.cwd), plan.stdin, timeout_seconds, env)
    parsed: object | None = None
    if plan.output_format == "json" and result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise UpstreamIntegrationError("upstream command returned malformed JSON") from error
    elif plan.output_format == "jsonl" and result.stdout.strip():
        rows: list[object] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise UpstreamIntegrationError(
                    "upstream command returned malformed JSONL"
                ) from error
        parsed = rows
    return CommandOutcome(
        state="SUCCEEDED" if result.returncode == 0 else "FAILED",
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        parsed=parsed,
    )
