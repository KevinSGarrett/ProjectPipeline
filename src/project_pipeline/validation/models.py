from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["ERROR", "WARNING", "INFO"]


@dataclass(slots=True, frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    path: str | None = None
    line: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ValidationReport:
    project_root: str
    findings: list[Finding] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        path: str | None = None,
        line: int | None = None,
    ) -> None:
        self.findings.append(Finding(severity, code, message, path, line))

    @property
    def errors(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "ERROR"]

    @property
    def warnings(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "WARNING"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "project_root": self.project_root,
            "ok": self.ok,
            "check_count": len(self.checks_run),
            "checks_run": self.checks_run,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [item.as_dict() for item in self.findings],
        }

    def render(self) -> str:
        lines = [
            f"Repository validation: {'PASS' if self.ok else 'FAIL'}",
            f"Checks: {len(self.checks_run)} | Errors: {len(self.errors)} | Warnings: {len(self.warnings)}",
        ]
        for item in sorted(
            self.findings,
            key=lambda value: (
                {"ERROR": 0, "WARNING": 1, "INFO": 2}[value.severity],
                value.code,
                value.path or "",
                value.line or 0,
            ),
        ):
            location = ""
            if item.path:
                location = f" [{item.path}"
                if item.line:
                    location += f":{item.line}"
                location += "]"
            lines.append(f"{item.severity} {item.code}{location}: {item.message}")
        return "\n".join(lines)
