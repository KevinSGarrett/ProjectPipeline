from __future__ import annotations

import importlib.util
import logging
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from project_pipeline import __version__
from project_pipeline.configuration import EffectiveConfiguration, ExternalWriteMode
from project_pipeline.observability import (
    configure_logging,
    correlation_scope,
    log_event,
    telemetry_status,
)
from project_pipeline.validation import RepositoryValidator


class BootstrapState(StrEnum):
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"
    READY = "READY"


@dataclass(frozen=True, slots=True)
class BootstrapCheck:
    check_id: str
    required: bool
    status: str
    message: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BootstrapReport:
    schema_version: str
    state: BootstrapState
    observed_at_utc: str
    project_version: str
    correlation_id: str
    configuration_fingerprint: str
    settings: dict[str, Any]
    checks: tuple[BootstrapCheck, ...]

    @property
    def ok(self) -> bool:
        return self.state is not BootstrapState.BLOCKED

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "ok": self.ok,
            "observed_at_utc": self.observed_at_utc,
            "project_version": self.project_version,
            "correlation_id": self.correlation_id,
            "configuration_fingerprint": self.configuration_fingerprint,
            "settings": self.settings,
            "checks": [asdict(check) for check in self.checks],
        }


def _tool_check(name: str, required: bool) -> BootstrapCheck:
    path = shutil.which(name)
    return BootstrapCheck(
        check_id=f"tool.{name}",
        required=required,
        status="PASS" if path else "UNAVAILABLE",
        message=f"{name} is {'available' if path else 'not available'}",
        details={"path": path},
    )


def _module_check(distribution: str, module: str) -> BootstrapCheck:
    available = importlib.util.find_spec(module) is not None
    return BootstrapCheck(
        check_id=f"dependency.{distribution}",
        required=True,
        status="PASS" if available else "FAIL",
        message=f"{distribution} is {'available' if available else 'unavailable'}",
        details={"module": module},
    )


def _nearest_existing_ancestor(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _directory_check(name: str, path: Path, prepare: bool) -> BootstrapCheck:
    if prepare:
        path.mkdir(parents=True, exist_ok=True)
    ancestor = path if path.exists() else _nearest_existing_ancestor(path.parent)
    writable = ancestor.exists() and os.access(ancestor, os.W_OK)
    ready = ancestor.exists() and writable
    return BootstrapCheck(
        check_id=f"path.{name}",
        required=True,
        status="PASS" if ready else "FAIL",
        message=f"runtime path {name} is {'ready' if ready else 'not writable'}",
        details={
            "path": str(path),
            "exists": path.exists(),
            "nearest_existing_ancestor": str(ancestor),
            "ancestor_exists": ancestor.exists(),
            "ancestor_writable": writable,
            "prepared": prepare,
        },
    )


def run_bootstrap(
    root: Path,
    configuration: EffectiveConfiguration,
    *,
    prepare: bool = False,
    validate_repository: bool = True,
    correlation_id: str = "corr:runtime-bootstrap",
) -> BootstrapReport:
    root = root.resolve()
    settings = configuration.settings
    logger = configure_logging(settings.logging)
    checks: list[BootstrapCheck] = [
        BootstrapCheck(
            check_id="runtime.python",
            required=True,
            status="PASS" if sys.version_info >= (3, 11) else "FAIL",
            message=f"Python {platform.python_version()}",
            details={"executable": sys.executable, "platform": platform.platform()},
        ),
        BootstrapCheck(
            check_id="runtime.root",
            required=True,
            status="PASS" if root.is_dir() else "FAIL",
            message=f"repository root {'exists' if root.is_dir() else 'is missing'}",
            details={"root": str(root)},
        ),
        _module_check("pydantic", "pydantic"),
        _module_check("opentelemetry-api", "opentelemetry.trace"),
        _module_check("opentelemetry-sdk", "opentelemetry.sdk.trace"),
        _tool_check("uv", required=False),
        _tool_check("ruff", required=False),
        _tool_check("mypy", required=False),
    ]
    for name, path in settings.runtime_paths(root).items():
        checks.append(_directory_check(name, path, prepare and settings.paths.create_on_boot))
    external_safe = (
        settings.security.external_writes_default
        in {
            ExternalWriteMode.DENY,
            ExternalWriteMode.DRY_RUN,
        }
        or settings.security.require_explicit_approval
    )
    checks.append(
        BootstrapCheck(
            check_id="security.external-writes",
            required=True,
            status="PASS" if external_safe else "FAIL",
            message="external mutation defaults preserve explicit authority",
            details={
                "mode": settings.security.external_writes_default.value,
                "require_explicit_approval": settings.security.require_explicit_approval,
            },
        )
    )
    checks.append(
        BootstrapCheck(
            check_id="telemetry.foundation",
            required=False,
            status="PASS",
            message="telemetry foundation inspected",
            details=telemetry_status(settings.telemetry).as_dict(),
        )
    )
    if validate_repository:
        validation = RepositoryValidator(root).validate()
        checks.append(
            BootstrapCheck(
                check_id="repository.contract",
                required=True,
                status="PASS" if validation.ok else "FAIL",
                message="repository contract validation completed",
                details={
                    "check_count": len(validation.checks_run),
                    "error_count": len(validation.errors),
                    "warning_count": len(validation.warnings),
                },
            )
        )
    failures = [check for check in checks if check.required and check.status != "PASS"]
    degraded = [check for check in checks if not check.required and check.status != "PASS"]
    state = (
        BootstrapState.BLOCKED
        if failures
        else BootstrapState.DEGRADED
        if degraded
        else BootstrapState.READY
    )
    with correlation_scope(project_id=settings.project_id, correlation_id=correlation_id):
        log_event(
            logger,
            logging.INFO if not failures else logging.ERROR,
            "runtime_bootstrap_completed",
            state=state.value,
            required_failure_count=len(failures),
            optional_unavailable_count=len(degraded),
            prepare=prepare,
            profile=settings.profile,
        )
    return BootstrapReport(
        schema_version="1.0.0",
        state=state,
        observed_at_utc=datetime.now(UTC).isoformat(),
        project_version=__version__,
        correlation_id=correlation_id,
        configuration_fingerprint=configuration.fingerprint(),
        settings=configuration.redacted_dict(),
        checks=tuple(checks),
    )
