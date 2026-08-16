from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


class WorktrunkAdapterError(RuntimeError):
    """Raised when Worktrunk execution or parsing fails."""


Runner = Callable[[Sequence[str], Path, float], subprocess.CompletedProcess[str]]


def _runner(argv: Sequence[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
    )


@dataclass(frozen=True, slots=True)
class WorktrunkPlan:
    argv: tuple[str, ...]
    cwd: str
    mutating: bool


class WorktrunkAdapter:
    """Optional Worktrunk CLI bridge kept behind Repository Steward approval."""

    def __init__(
        self, executable: str = "wt", *, runner: Runner = _runner, timeout_seconds: float = 60.0
    ) -> None:
        self.executable = executable
        self.runner = runner
        self.timeout_seconds = timeout_seconds

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def list_plan(self, root: Path) -> WorktrunkPlan:
        return WorktrunkPlan((self.executable, "list", "--format=json"), str(root), False)

    def create_plan(
        self, root: Path, branch: str, *, base: str | None = None, no_hooks: bool = True
    ) -> WorktrunkPlan:
        if not branch or branch.startswith("-"):
            raise ValueError("branch must be a non-option name")
        argv = [self.executable, "switch", "--create", branch, "--no-cd"]
        if base:
            if base.startswith("-"):
                raise ValueError("base must not be an option")
            argv.extend(["--base", base])
        if no_hooks:
            argv.append("--no-hooks")
        return WorktrunkPlan(tuple(argv), str(root), True)

    def remove_plan(self, root: Path, branch: str) -> WorktrunkPlan:
        if not branch or branch.startswith("-"):
            raise ValueError("branch must be a non-option name")
        return WorktrunkPlan((self.executable, "remove", branch), str(root), True)

    def execute(self, plan: WorktrunkPlan, *, approved: bool = False) -> dict[str, object]:
        if plan.mutating and not approved:
            return {"state": "DRY_RUN", "argv": list(plan.argv), "cwd": plan.cwd}
        result = self.runner(plan.argv, Path(plan.cwd), self.timeout_seconds)
        if result.returncode != 0:
            raise WorktrunkAdapterError(
                f"Worktrunk exited {result.returncode}: {result.stderr.strip()}"
            )
        output: object = result.stdout
        if not plan.mutating and plan.argv[-1] == "--format=json":
            try:
                output = json.loads(result.stdout or "[]")
            except json.JSONDecodeError as error:
                raise WorktrunkAdapterError("Worktrunk list returned malformed JSON") from error
        return {"state": "APPLIED" if plan.mutating else "OBSERVED", "output": output}
