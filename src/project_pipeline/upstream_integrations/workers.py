from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project_pipeline.contracts.envelopes import ActionIntent
from project_pipeline.upstream_integrations.common import (
    CommandOutcome,
    CommandPlan,
    Runner,
    default_runner,
    executable_available,
    execute_plan,
)


@dataclass(slots=True)
class CodexExecAdapter:
    executable: str = "codex"
    runner: Runner = default_runner
    timeout_seconds: float = 900.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan(
        self,
        root: Path,
        prompt: str,
        *,
        mutating: bool = False,
        model: str | None = None,
        output_schema: Path | None = None,
    ) -> CommandPlan:
        root = root.resolve()
        argv = [
            self.executable,
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--cd",
            str(root),
        ]
        if model:
            argv.extend(["--model", model])
        if output_schema:
            schema = output_schema.resolve()
            schema.relative_to(root)
            argv.extend(["--output-schema", str(schema)])
        if mutating:
            argv.append("--approve-for-me")
        else:
            argv.extend(["--sandbox", "read-only"])
        argv.append("-")
        forbidden = {
            "--dangerously-bypass-approvals-and-sandbox",
            "--dangerously-bypass-hook-trust",
        }
        if forbidden.intersection(argv):
            raise ValueError("unsafe Codex bypass flag is forbidden")
        return CommandPlan(
            upstream_id="UPSTREAM-073",
            argv=tuple(argv),
            cwd=str(root),
            mutating=mutating,
            network_required=True,
            stdin=prompt,
            output_format="jsonl",
            evidence_sources=(
                "openai/codex:codex-rs/exec/src/cli.rs",
                "openai/codex:codex-rs/utils/cli/src/shared_options.rs",
            ),
        )

    def execute(
        self,
        plan: CommandPlan,
        *,
        allow_network: bool = False,
        intent: ActionIntent | None = None,
    ) -> CommandOutcome:
        return execute_plan(
            plan,
            runner=self.runner,
            timeout_seconds=self.timeout_seconds,
            allow_network=allow_network,
            intent=intent,
        )


@dataclass(slots=True)
class GeminiCliAdapter:
    executable: str = "gemini"
    runner: Runner = default_runner
    timeout_seconds: float = 900.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan(
        self,
        root: Path,
        prompt: str,
        *,
        mutating: bool = False,
        model: str | None = None,
    ) -> CommandPlan:
        root = root.resolve()
        argv = [self.executable, "-p", prompt, "--output-format", "stream-json", "--sandbox"]
        argv.extend(["--approval-mode", "auto_edit" if mutating else "plan"])
        if model:
            argv.extend(["--model", model])
        if "yolo" in argv or "--yolo" in argv:
            raise ValueError("Gemini yolo mode is forbidden")
        return CommandPlan(
            upstream_id="UPSTREAM-045",
            argv=tuple(argv),
            cwd=str(root),
            mutating=mutating,
            network_required=True,
            output_format="jsonl",
            evidence_sources=(
                "google-gemini/gemini-cli:docs/cli/headless.md",
                "google-gemini/gemini-cli:docs/cli/cli-reference.md",
            ),
        )

    def execute(
        self,
        plan: CommandPlan,
        *,
        allow_network: bool = False,
        intent: ActionIntent | None = None,
    ) -> CommandOutcome:
        return execute_plan(
            plan,
            runner=self.runner,
            timeout_seconds=self.timeout_seconds,
            allow_network=allow_network,
            intent=intent,
        )
