from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_instruction_validator(root: Path) -> Any:
    path = root / "scripts/validate_instructions.py"
    module_name = "_project_pipeline_instruction_validator"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load instruction validator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build_cold_start(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = load(root / "instructions/INSTRUCTION_MANIFEST.json")
    coverage = load(root / "instructions/INSTRUCTION_COVERAGE_MATRIX.json")
    scenarios = load(root / "instructions/policies/VALIDATION_SCENARIOS.json")
    validator = load_instruction_validator(root)
    instruction_report = validator.validate_instruction_system(root)
    first_read = list(validator.MANDATORY_BOOTSTRAP)
    required = [
        *(root / path for path in first_read),
        root / "config/project.json",
        root / "plans/PLAN_CATALOG.json",
        root / "jira/BOARD_MANIFEST.json",
    ]
    missing = [path.relative_to(root).as_posix() for path in required if not path.exists()]
    commands = [
        item["command"]
        for item in manifest.get("commands", [])
        if isinstance(item, dict) and item.get("command")
    ]
    domains = {
        item["domain"]: item["primary"]
        for item in coverage.get("domains", [])
        if isinstance(item, dict)
    }
    return {
        "schema_version": "1.0.0",
        "ready": not missing and instruction_report.ok,
        "missing": missing,
        "instruction_validation": {
            "ok": instruction_report.ok,
            "error_count": len(instruction_report.errors),
            "warning_count": len(instruction_report.warnings),
        },
        "identity": {
            "project": manifest.get("project_name"),
            "project_id": manifest.get("project_id"),
            "repository": manifest.get("repository_url"),
            "canonical_local_root": manifest.get("canonical_local_root"),
        },
        "first_read": first_read,
        "preflight_commands": commands,
        "routing": domains,
        "hard_stops": [
            "Oracle or hidden-evaluator material",
            "missing or exposed credential",
            "unknown remote write outcome",
            "destructive operation against unpreserved work",
            "failed required gate",
            "irreconcilable material authority conflict",
            "split-brain or stale-fencing risk",
            "budget or policy denial",
        ],
        "durable_state": [
            "source control",
            "local Jira mirror",
            "project-state database",
            "control snapshots",
            "orchestration checkpoints and outbox",
            "resource leases and fencing",
            "evidence ledger",
            "manifests",
        ],
        "scenario_ids": [
            item.get("id") for item in scenarios.get("scenarios", []) if isinstance(item, dict)
        ],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        "ProjectPipeline cold start",
        f"Ready: {payload['ready']}",
        f"Identity: {payload['identity']['project']} / {payload['identity']['project_id']}",
        f"Repository: {payload['identity']['repository']}",
        "First read:",
    ]
    lines.extend(f"  {index}. {path}" for index, path in enumerate(payload["first_read"], 1))
    lines.append("Preflight:")
    lines.extend(f"  - {command}" for command in payload["preflight_commands"])
    lines.append("Hard stops:")
    lines.extend(f"  - {item}" for item in payload["hard_stops"])
    if not payload["instruction_validation"]["ok"]:
        lines.append(
            "Instruction validation: "
            f"FAIL ({payload['instruction_validation']['error_count']} errors, "
            f"{payload['instruction_validation']['warning_count']} warnings)"
        )
    if payload["missing"]:
        lines.append("Missing required paths:")
        lines.extend(f"  - {item}" for item in payload["missing"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a no-chat ProjectPipeline cold-start route")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = build_cold_start(args.root)
    except (OSError, json.JSONDecodeError, KeyError) as error:
        print(f"Cold start failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else render(payload))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
