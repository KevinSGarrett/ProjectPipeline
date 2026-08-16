from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project_pipeline.upstream_integrations.common import (
    CommandOutcome,
    CommandPlan,
    Runner,
    confined,
    default_runner,
    executable_available,
    execute_plan,
    require_safe_value,
)


@dataclass(slots=True)
class PromptfooAdapter:
    executable: str = "promptfoo"
    runner: Runner = default_runner
    timeout_seconds: float = 1200.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_eval(
        self,
        root: Path,
        config: Path,
        output: Path,
        *,
        max_concurrency: int = 1,
        network_required: bool = True,
    ) -> CommandPlan:
        root = root.resolve()
        config_path = confined(root, config, must_exist=True)
        output_path = confined(root, output)
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        argv = (
            self.executable,
            "eval",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--max-concurrency",
            str(max_concurrency),
            "--no-share",
            "--no-progress-bar",
            "--no-table",
        )
        return CommandPlan(
            upstream_id="UPSTREAM-085",
            argv=argv,
            cwd=str(root),
            mutating=False,
            network_required=network_required,
            output_format="text",
            evidence_sources=("promptfoo/promptfoo:site/docs/usage/command-line.md",),
            metadata={"result_path": str(output_path)},
        )

    def execute(self, plan: CommandPlan, *, allow_network: bool = False) -> CommandOutcome:
        return execute_plan(
            plan,
            runner=self.runner,
            timeout_seconds=self.timeout_seconds,
            allow_network=allow_network,
        )


@dataclass(slots=True)
class InspectAIAdapter:
    executable: str = "inspect"
    runner: Runner = default_runner
    timeout_seconds: float = 1200.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan_eval(
        self,
        root: Path,
        task: str,
        *,
        model: str,
        log_dir: Path,
        network_required: bool = True,
    ) -> CommandPlan:
        root = root.resolve()
        task = require_safe_value(task, field_name="task")
        model = require_safe_value(model, field_name="model")
        logs = confined(root, log_dir)
        argv = (
            self.executable,
            "eval",
            task,
            "--model",
            model,
            "--log-dir",
            str(logs),
        )
        return CommandPlan(
            upstream_id="UPSTREAM-108",
            argv=argv,
            cwd=str(root),
            mutating=False,
            network_required=network_required,
            output_format="text",
            evidence_sources=(
                "UKGovernmentBEIS/inspect_ai:README.md",
                "UKGovernmentBEIS/inspect_ai:src/inspect_ai/_cli/eval.py",
            ),
            metadata={"log_dir": str(logs)},
        )

    def execute(self, plan: CommandPlan, *, allow_network: bool = False) -> CommandOutcome:
        return execute_plan(
            plan,
            runner=self.runner,
            timeout_seconds=self.timeout_seconds,
            allow_network=allow_network,
        )
