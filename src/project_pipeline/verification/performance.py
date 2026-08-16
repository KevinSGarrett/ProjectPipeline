from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from project_pipeline.domain.verification import PerformanceResult, verification_identifier


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def measure_callable(
    subject: str,
    callback: Callable[[], object],
    *,
    samples: int,
    p95_budget_ms: int,
) -> PerformanceResult:
    values: list[int] = []
    for _ in range(samples):
        started = time.perf_counter()
        callback()
        values.append(max(0, int((time.perf_counter() - started) * 1000)))
    p50 = _percentile(values, 0.50)
    p95 = _percentile(values, 0.95)
    max_ms = max(values)
    return PerformanceResult(
        performance_id=verification_identifier("PERF", subject, str(samples), str(p95_budget_ms)),
        subject=subject,
        sample_count=samples,
        p50_ms=p50,
        p95_ms=p95,
        max_ms=max_ms,
        budget_p95_ms=p95_budget_ms,
        passed=p95 <= p95_budget_ms,
    )


def repository_validation_performance(root: Path, *, samples: int) -> PerformanceResult:
    def run() -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "project_pipeline", "validate", "--root", str(root)],
            cwd=root,
            env={**__import__("os").environ, "PYTHONPATH": str(root / "src")},
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"repository validation failed during performance sample: {completed.stdout}{completed.stderr}"
            )

    return measure_callable(
        "repository-validator",
        run,
        samples=samples,
        p95_budget_ms=7000,
    )


def cli_help_performance(root: Path, *, samples: int, p95_budget_ms: int) -> PerformanceResult:
    def run() -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "project_pipeline", "--help"],
            cwd=root,
            env={**__import__("os").environ, "PYTHONPATH": str(root / "src")},
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"CLI help failed: {completed.stderr}")

    return measure_callable(
        "project-pipeline-cli-help",
        run,
        samples=samples,
        p95_budget_ms=p95_budget_ms,
    )
