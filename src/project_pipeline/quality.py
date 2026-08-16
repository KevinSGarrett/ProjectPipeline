from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from project_pipeline.contracts import validate_schemas
from project_pipeline.dependencies import validate_dependency_lock
from project_pipeline.validation import RepositoryValidator


class QualityState(StrEnum):
    FAIL = "FAIL"
    PASS = "PASS"
    PASS_WITH_UNAVAILABLE = "PASS_WITH_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class QualityCheck:
    check_id: str
    required: bool
    status: str
    command: tuple[str, ...]
    return_code: int | None
    output: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    schema_version: str
    state: QualityState
    checks: tuple[QualityCheck, ...]

    @property
    def ok(self) -> bool:
        return self.state is not QualityState.FAIL

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "ok": self.ok,
            "checks": [asdict(check) for check in self.checks],
        }


def _run_command(
    check_id: str,
    command: Sequence[str],
    root: Path,
    *,
    required: bool,
) -> QualityCheck:
    executable = command[0]
    if executable != sys.executable and shutil.which(executable) is None:
        return QualityCheck(
            check_id=check_id,
            required=required,
            status="UNAVAILABLE",
            command=tuple(command),
            return_code=None,
            output=f"executable is unavailable: {executable}",
        )
    completed = subprocess.run(list(command), cwd=root, capture_output=True, check=False, text=True)
    combined = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return QualityCheck(
        check_id=check_id,
        required=required,
        status="PASS" if completed.returncode == 0 else "FAIL",
        command=tuple(command),
        return_code=completed.returncode,
        output=combined,
    )


def _repository_check(root: Path) -> QualityCheck:
    report = RepositoryValidator(root).validate()
    return QualityCheck(
        check_id="repository",
        required=True,
        status="PASS" if report.ok else "FAIL",
        command=(sys.executable, "-m", "project_pipeline", "validate", "--root", "."),
        return_code=0 if report.ok else 1,
        output=report.render(),
    )


def _dependency_check(root: Path) -> QualityCheck:
    errors = validate_dependency_lock(root)
    return QualityCheck(
        check_id="dependencies",
        required=True,
        status="PASS" if not errors else "FAIL",
        command=("internal", "dependency-lock-validation"),
        return_code=0 if not errors else 1,
        output="\n".join(errors) if errors else "dependency lock and exports are consistent",
    )


def _schema_check(root: Path) -> QualityCheck:
    errors = validate_schemas(root)
    return QualityCheck(
        check_id="schemas",
        required=True,
        status="PASS" if not errors else "FAIL",
        command=("internal", "generated-schema-validation"),
        return_code=0 if not errors else 1,
        output="\n".join(errors) if errors else "generated schemas are current",
    )


def run_quality(root: Path, *, strict_tools: bool = False, coverage: bool = False) -> QualityReport:
    root = root.resolve()
    test_command = (
        (
            "pytest",
            "-q",
            "--cov=project_pipeline",
            "--cov-report=term-missing",
            "--cov-fail-under=70",
        )
        if coverage
        else ("pytest", "-q")
    )
    checks: list[QualityCheck] = [
        _run_command(
            "compile",
            (sys.executable, "-m", "compileall", "-q", "-f", "src", "tests"),
            root,
            required=True,
        ),
        _run_command("tests", test_command, root, required=True),
        _dependency_check(root),
        _schema_check(root),
        _repository_check(root),
        _run_command("ruff-check", ("ruff", "check", "src", "tests"), root, required=strict_tools),
        _run_command(
            "ruff-format",
            ("ruff", "format", "--check", "src", "tests"),
            root,
            required=strict_tools,
        ),
        _run_command("mypy", ("mypy",), root, required=strict_tools),
    ]
    failures = [
        check
        for check in checks
        if check.status == "FAIL" or (check.required and check.status == "UNAVAILABLE")
    ]
    unavailable = [check for check in checks if check.status == "UNAVAILABLE"]
    state = (
        QualityState.FAIL
        if failures
        else QualityState.PASS_WITH_UNAVAILABLE
        if unavailable
        else QualityState.PASS
    )
    return QualityReport(schema_version="1.0.0", state=state, checks=tuple(checks))


def write_quality_report(report: QualityReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
