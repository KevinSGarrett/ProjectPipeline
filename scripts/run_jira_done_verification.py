from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ISSUE_DIRS = ("epics", "stories", "tasks", "subtasks")


def _issues(root: Path) -> list[dict]:
    rows: list[dict] = []
    for directory in ISSUE_DIRS:
        for path in sorted((root / "jira" / directory).glob("PP-*.json")):
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def _run(argv: list[str], root: Path, timeout: int) -> tuple[str, int | None, float, str]:
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
        stdout, stderr = process.communicate(timeout=timeout)
        status = "PASS" if process.returncode == 0 else "FAIL"
        detail = (stdout + "\n" + stderr)[-12000:]
        return status, process.returncode, time.monotonic() - started, detail
    except subprocess.TimeoutExpired as exc:
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
        detail = ((exc.stdout or "") + "\n" + (exc.stderr or "") + stdout + "\n" + stderr)[-12000:]
        return "TIMEOUT", None, time.monotonic() - started, detail


def _argv(command: str, root: Path) -> list[list[str]]:
    parts: list[list[str]] = []
    for segment in command.split("&&"):
        segment = segment.strip()
        if segment.startswith("PYTHONPATH=src "):
            segment = segment[len("PYTHONPATH=src ") :]
        tokens = shlex.split(segment, posix=True)
        if tokens and tokens[0] in {"python", "python3"}:
            tokens[0] = sys.executable
        expanded: list[str] = []
        for token in tokens:
            if "*" in token and not token.startswith("-"):
                matches = sorted(str(path.relative_to(root)) for path in root.glob(token))
                expanded.extend(matches or [token])
            else:
                expanded.append(token)
        parts.append(expanded)
    return parts


def _case_name(case: ET.Element) -> str:
    name = case.attrib.get("name", "").split("[")[0]
    class_name = case.attrib.get("classname", "").split(".")[-1]
    return f"{class_name}.{name}" if class_name and class_name != name else name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-file-timeout", type=int, default=60)
    parser.add_argument("--command-timeout", type=int, default=180)
    parser.add_argument("--reuse-junit", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    run_dir = output.parent / "completion_verification_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    generated_at = (
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    )

    done = [item for item in _issues(root) if item["state"] == "DONE"]
    catalog = json.loads((root / "tests" / "TEST_CATALOG.json").read_text(encoding="utf-8"))[
        "tests"
    ]
    required_ids = {test_id for item in done for test_id in item.get("required_tests", [])}
    selected = [entry for entry in catalog if entry["test_id"] in required_ids]
    by_file: dict[str, list[dict]] = {}
    for entry in selected:
        by_file.setdefault(entry["path"], []).append(entry)

    test_results: dict[str, dict] = {}
    file_runs: list[dict] = []
    command_results: dict[str, dict] = {}

    def checkpoint() -> None:
        payload = {
            "schema_version": "1.0.0",
            "generated_at_utc": generated_at,
            "candidate_done_count": len(done),
            "required_test_count": len(required_ids),
            "test_results": test_results,
            "file_runs": file_runs,
            "command_results": command_results,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for index, (path, entries) in enumerate(sorted(by_file.items()), start=1):
        digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
        xml_path = run_dir / f"{digest}.xml"
        if path.endswith(".mjs"):
            run_argv = ["node", "--test", path]
        elif path.startswith("scripts/") and path.endswith(".py"):
            run_argv = [sys.executable, path]
        else:
            run_argv = [sys.executable, "-m", "pytest", "-q", path, f"--junitxml={xml_path}"]
        if args.reuse_junit and xml_path.exists() and path.startswith("tests/"):
            cases = list(ET.parse(xml_path).iter("testcase"))
            status = (
                "FAIL"
                if any(
                    case.find("failure") is not None or case.find("error") is not None
                    for case in cases
                )
                else "PASS"
            )
            returncode, duration, detail = (
                (1 if status == "FAIL" else 0),
                0.0,
                "reused prior fresh JUnit result",
            )
        else:
            status, returncode, duration, detail = _run(
                run_argv,
                root,
                args.per_file_timeout,
            )
        observed: dict[str, str] = {}
        if xml_path.exists():
            for case in ET.parse(xml_path).iter("testcase"):
                outcome = "PASS"
                if case.find("failure") is not None or case.find("error") is not None:
                    outcome = "FAIL"
                elif case.find("skipped") is not None:
                    outcome = "SKIP"
                observed[_case_name(case)] = outcome
                observed[case.attrib.get("name", "").split("[")[0]] = outcome
        for entry in entries:
            outcome = observed.get(entry["callable"])
            if outcome is None and "." in entry["callable"]:
                outcome = observed.get(entry["callable"].split(".")[-1])
            test_results[entry["test_id"]] = {
                "status": outcome or status,
                "path": path,
                "callable": entry["callable"],
                "file_run_status": status,
            }
        file_runs.append(
            {
                "path": path,
                "status": status,
                "returncode": returncode,
                "duration_seconds": round(duration, 3),
                "detail_tail": detail,
                "progress": f"{index}/{len(by_file)}",
            }
        )
        print(f"[{index}/{len(by_file)}] {status} {path}", flush=True)
        checkpoint()

    commands = sorted(
        {
            criterion["verification"]["command"]
            for item in done
            for criterion in item.get("acceptance_criteria", [])
        }
    )
    for index, command in enumerate(commands, start=1):
        aggregate = "PASS"
        steps: list[dict] = []
        for argv in _argv(command, root):
            status, returncode, duration, detail = _run(argv, root, args.command_timeout)
            steps.append(
                {
                    "argv": argv,
                    "status": status,
                    "returncode": returncode,
                    "duration_seconds": round(duration, 3),
                    "detail_tail": detail,
                }
            )
            if status != "PASS":
                aggregate = status
                break
        command_results[command] = {"status": aggregate, "steps": steps}
        print(f"[command {index}/{len(commands)}] {aggregate} {command}", flush=True)
        checkpoint()

    checkpoint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
