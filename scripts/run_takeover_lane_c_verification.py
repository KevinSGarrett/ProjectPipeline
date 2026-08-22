from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class VerificationGroup:
    name: str
    argv: list[str]
    diagnostic_argv: list[str] | None = None


def _run(argv: list[str], root: Path, timeout_seconds: int) -> dict[str, object]:
    started = time.monotonic()
    process = subprocess.Popen(
        argv,
        cwd=root,
        env={**os.environ, "PYTHONPATH": "src"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        elapsed = round(time.monotonic() - started, 3)
        status = "PASS" if process.returncode == 0 else "FAIL"
        return {
            "status": status,
            "returncode": process.returncode,
            "duration_seconds": elapsed,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            process.kill()
        stdout, stderr = process.communicate()
        elapsed = round(time.monotonic() - started, 3)
        return {
            "status": "TIMEOUT",
            "returncode": None,
            "duration_seconds": elapsed,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
        }


def _default_groups(root: Path) -> list[VerificationGroup]:
    groups = [
        VerificationGroup(
            name="pp380_transfer_trio",
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_docker_mcp_gateway.py",
                "tests/test_litellm_adapter.py",
                "tests/test_pydantic_ai_adapter.py",
            ],
            diagnostic_argv=[
                sys.executable,
                "-m",
                "pytest",
                "-vv",
                "--maxfail=1",
                "tests/test_docker_mcp_gateway.py",
                "tests/test_litellm_adapter.py",
                "tests/test_pydantic_ai_adapter.py",
            ],
        ),
        VerificationGroup(
            name="takeover_lane_invariants_meta",
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_takeover_lane_invariants_meta.py",
            ],
            diagnostic_argv=[
                sys.executable,
                "-m",
                "pytest",
                "-vv",
                "--maxfail=1",
                "tests/test_takeover_lane_invariants_meta.py",
            ],
        ),
    ]
    takeover_governor_path = root / "tests" / "test_takeover_governor.py"
    if takeover_governor_path.exists():
        groups.append(
            VerificationGroup(
                name="takeover_governor_regression",
                argv=[
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    str(takeover_governor_path.relative_to(root)),
                ],
                diagnostic_argv=[
                    sys.executable,
                    "-m",
                    "pytest",
                    "-vv",
                    "--maxfail=1",
                    str(takeover_governor_path.relative_to(root)),
                ],
            )
        )
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Lane C verification pack with timings.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evidence/lane_c_verification_report.json"),
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    groups = _default_groups(root)
    report: dict[str, object] = {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "repeat": args.repeat,
        "timeout_seconds": args.timeout_seconds,
        "groups": [],
    }
    overall_ok = True

    for group in groups:
        runs: list[dict[str, object]] = []
        statuses: list[str] = []
        for run_index in range(1, args.repeat + 1):
            result = _run(group.argv, root, args.timeout_seconds)
            result["run_index"] = run_index
            runs.append(result)
            statuses.append(str(result["status"]))
            print(
                f"[{group.name}] run {run_index}/{args.repeat}: "
                f"{result['status']} in {result['duration_seconds']}s",
                flush=True,
            )
            if result["status"] != "PASS":
                overall_ok = False

        flaky = len(set(statuses)) > 1
        failed = any(status != "PASS" for status in statuses)
        diagnostics = None
        if failed and group.diagnostic_argv is not None:
            diagnostics = _run(group.diagnostic_argv, root, args.timeout_seconds)

        report["groups"].append(
            {
                "name": group.name,
                "command": group.argv,
                "statuses": statuses,
                "flaky": flaky,
                "runs": runs,
                "diagnostics": diagnostics,
            }
        )

    report["overall_status"] = "PASS" if overall_ok else "FAIL"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote report: {output}", flush=True)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
