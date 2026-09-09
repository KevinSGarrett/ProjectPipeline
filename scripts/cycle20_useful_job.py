"""Bounded selected-work runner. Metadata-only receipts are not acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

CRITERIA = {
    "PP-TASK-000516": ("AC-PP-000516-01", "AC-PP-000516-02", "AC-PP-000516-03", "AC-PP-000516-04"),
    "PP-TASK-000517": ("AC-PP-000517-01", "AC-PP-000517-02", "AC-PP-000517-03", "AC-PP-000517-04"),
    "PP-TASK-000519": ("AC-PP-000519-01", "AC-PP-000519-02", "AC-PP-000519-03"),
}
BINDINGS = {
    "PP-TASK-000516": {
        "implementation_paths": (
            "src/project_pipeline/autonomy_runtime/remote_worker_protocol.py",
            "src/project_pipeline/autonomy_runtime/windows_limits.py",
            "src/project_pipeline/autonomy_runtime/ssh_dispatch.py",
            "src/project_pipeline/autonomy_runtime/durable_jobs.py",
            "src/project_pipeline/autonomy_runtime/dispatch_workflow.py",
        ),
        "required_tests": (
            "tests/test_cycle20_pm_falsifiers.py",
            "tests/test_cycle20_remote_durability.py",
        ),
    },
    "PP-TASK-000517": {
        "implementation_paths": (
            "src/project_pipeline/autonomy_runtime/managed_worker.py",
            "src/project_pipeline/scheduler/host_observation.py",
        ),
        "required_tests": ("tests/test_cycle20_host_admission.py",),
    },
    "PP-TASK-000519": {
        "implementation_paths": (
            "src/project_pipeline/autonomy_runtime/observation_eval.py",
            "src/project_pipeline/autonomy_runtime/lifecycle.py",
            "src/project_pipeline/autonomy_runtime/fleet_loop.py",
        ),
        "required_tests": ("tests/test_cycle20_pm_falsifiers.py",),
    },
}
STRUCTURAL_PARENTS = frozenset({"PP-STORY-000065", "PP-STORY-000396"})


def _worker_src() -> Path | None:
    raw = os.environ.get("PP_WORKER_SRC", "").strip()
    return Path(raw) if raw else None


def _repo(root: Path | None) -> Path:
    if root is not None:
        return root
    src = _worker_src()
    if src is not None:
        return src.parent if src.name == "src" else src
    return Path(__file__).resolve().parents[1]


def _resolve(repo: Path, relative: str) -> Path:
    candidate = repo / relative
    if candidate.is_file():
        return candidate
    src = _worker_src()
    if src is not None:
        stripped = relative.removeprefix("src/")
        for option in (src / relative, src / stripped, src.parent / relative):
            if option.is_file():
                return option
    return candidate


def _emit(output: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, sort_keys=True))
    return artifact


def run(*, job_id: str, output: Path, root: Path | None = None) -> dict[str, Any]:
    repo = _repo(root)
    if (
        job_id in STRUCTURAL_PARENTS
        or job_id.startswith("PP-STORY-")
        or job_id.startswith("PP-EPIC-")
    ):
        return _emit(
            output,
            {
                "ok": False,
                "job_id": job_id,
                "reason": "structural_parent_not_selected_work",
            },
        )
    binding = BINDINGS.get(job_id)
    if binding is None:
        return _emit(
            output,
            {
                "ok": False,
                "job_id": job_id,
                "reason": "unknown_selected_work",
            },
        )
    files: list[dict[str, str | int]] = []
    missing: list[str] = []
    hasher = hashlib.sha256()
    for relative in binding["implementation_paths"]:
        path = _resolve(repo, relative)
        if not path.is_file():
            missing.append(relative)
            continue
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(payload)
        files.append({"path": relative, "sha256": digest, "bytes": len(payload)})
    tests: list[str] = []
    for relative in binding["required_tests"]:
        path = _resolve(repo, relative)
        if not path.is_file():
            missing.append(relative)
            continue
        tests.append(relative)
    artifact = {
        "ok": not missing,
        "job_id": job_id,
        "criterion_ids": list(CRITERIA.get(job_id, ())),
        "verifier": "implementation_and_test_binding",
        "implementation_paths": files,
        "required_tests": tests,
        "missing": missing,
        "artifact_sha256": hasher.hexdigest(),
        "bytes": sum(int(item["bytes"]) for item in files),
    }
    if missing:
        artifact["reason"] = "selected_implementation_or_test_missing"
    return _emit(output, artifact)


def main() -> int:
    parser = argparse.ArgumentParser(prog="cycle20-useful-job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("useful_artifact.json"))
    args = parser.parse_args()
    result = run(job_id=args.job_id, output=args.output)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
