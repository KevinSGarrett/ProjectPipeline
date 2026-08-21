"""Non-duration qualification contract for REQ-PDEF-0011.

Duration, publication, and Completion Gate remain after these stages pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl

NON_DURATION_STAGES = (
    "unit_contract",
    "isolated_git_worktree",
    "local_real_integrated",
    "authorized_github_jira",
    "qualified_provider_dispatch",
    "recovery_restart_worker_loss",
    "windows_service_command_center",
    "continuous_next_work_external_precondition",
    "release_finalization_semantic_gates",
)

REMAINING_ACCEPTANCE = (
    "real 4h qualification",
    "real 24h qualification",
    "subsequent real 72h qualification",
    "release publication",
    "post-release verification",
    "Completion Gate",
)

STAGE_CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "unit_contract": {
        "implementation_paths": (
            "src/project_pipeline/validation/repository.py",
            "src/project_pipeline/validation/product_outcome.py",
        ),
        "test_ids": ("TEST-PDEF-OUTCOME-001", "TEST-REPOSITORY-001"),
    },
    "isolated_git_worktree": {
        "implementation_paths": ("src/project_pipeline/github_steward/local_git.py",),
        "test_ids": ("TEST-PDEF-NONDUR-002",),
    },
    "local_real_integrated": {
        "implementation_paths": ("src/project_pipeline/autonomy_runtime/live_qualification.py",),
        "test_ids": ("TEST-PDEF-NONDUR-001",),
    },
    "authorized_github_jira": {
        "implementation_paths": (
            "src/project_pipeline/github_steward/merge_gate.py",
            "src/project_pipeline/jira_steward/identity.py",
        ),
        "test_ids": ("TEST-PDEF-NONDUR-001",),
    },
    "qualified_provider_dispatch": {
        "implementation_paths": ("src/project_pipeline/agent_router/router.py",),
        "test_ids": ("TEST-PDEF-NONDUR-001",),
    },
    "recovery_restart_worker_loss": {
        "implementation_paths": (
            "src/project_pipeline/lifecycle/attestation_recovery.py",
            "src/project_pipeline/command_center/autonomy_director.py",
        ),
        "test_ids": ("TEST-CTRL-DIRECTOR-001", "TEST-PDEF-NONDUR-001"),
    },
    "windows_service_command_center": {
        "implementation_paths": (
            "src/project_pipeline/autonomy_runtime/windows_service.py",
            "src/project_pipeline/command_center/live_server.py",
        ),
        "test_ids": ("TEST-INFRA-SVC-001", "TEST-CC-LIVE-001"),
    },
    "continuous_next_work_external_precondition": {
        "implementation_paths": (
            "src/project_pipeline/scheduler/productive_idle.py",
            "src/project_pipeline/command_center/autonomy_director.py",
        ),
        "test_ids": ("TEST-SCHED-IDLE-001", "TEST-CTRL-DIRECTOR-001"),
    },
    "release_finalization_semantic_gates": {
        "implementation_paths": (
            "src/project_pipeline/release_hardening/disposable_rehearsal.py",
            "src/project_pipeline/lifecycle/cycle_handoff.py",
        ),
        "test_ids": ("TEST-REL-REHEARSE-001", "TEST-PDEF-NONDUR-003"),
    },
}


def _catalog_ids(root: Path) -> set[str]:
    catalog = read_json(root / "tests" / "TEST_CATALOG.json")
    return {str(item.get("test_id")) for item in catalog.get("tests", [])}


def evaluate_nonduration_qualification(root: Path) -> dict[str, Any]:
    """Prove every non-time stage is implemented and mapped; never claim IMPLEMENTED."""

    root = root.resolve()
    catalog_ids = _catalog_ids(root)
    requirements = {
        str(item.get("requirement_id")): item
        for item in read_jsonl(root / "plans/_traceability/requirements.jsonl")
    }
    core = requirements.get("REQ-PDEF-0011") or {}
    stages: list[dict[str, Any]] = []
    missing: list[str] = []
    for stage in NON_DURATION_STAGES:
        contract = STAGE_CONTRACTS[stage]
        path_ok = all((root / relative).is_file() for relative in contract["implementation_paths"])
        tests_ok = all(test_id in catalog_ids for test_id in contract["test_ids"])
        if not path_ok:
            missing.append(f"{stage}: implementation path missing")
        if not tests_ok:
            missing.append(f"{stage}: required test mapping missing")
        stages.append(
            {
                "stage": stage,
                "implementation_paths": list(contract["implementation_paths"]),
                "test_ids": list(contract["test_ids"]),
                "present": path_ok and tests_ok,
            }
        )
    allowed_states = {"PLANNED_ONLY", "PARTIALLY_IMPLEMENTED"}
    if core.get("implementation_state") not in allowed_states:
        missing.append("REQ-PDEF-0011 cannot be IMPLEMENTED before duration and release stages")
    return {
        "schema_version": "1.0.0",
        "requirement_id": "REQ-PDEF-0011",
        "ok": not missing,
        "implementation_state": "PARTIALLY_IMPLEMENTED",
        "stages": stages,
        "remaining_acceptance": list(REMAINING_ACCEPTANCE),
        "missing": missing,
    }
