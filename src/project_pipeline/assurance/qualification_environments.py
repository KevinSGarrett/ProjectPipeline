"""Compile current-SHA/tree qualification for Completion Gate environments.

Ancestor, mock, and differently headed receipts fail closed. Duration and
publication environments are reported as remaining, never inherited.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.campaign import (
    REQUIRED_PP384_STAGES,
    inspect_worktree_identity,
)
from project_pipeline.autonomy_runtime.nonduration import evaluate_nonduration_qualification
from project_pipeline.io import read_json, write_json

DEFAULT_LIVE_QUALIFICATION_PATH = (
    "evidence/autonomy_runtime/live_qualification/live_qualification_latest.json"
)

NON_DURATION_ENVIRONMENTS = (
    "authorized_github_jira_sandbox_or_live",
    "deterministic_unit_and_contract",
    "isolated_real_git_worktree_journey",
    "local_real_integrated_journey",
    "qualified_real_worker_provider_dispatch",
    "recovery_and_restart",
    "windows_service_and_command_center",
)

DURATION_OR_RELEASE_ENVIRONMENTS = (
    "unattended_24_hour",
    "unattended_72_hour",
    "released_post_release_completion_gate",
)

UnitContractProbe = Callable[[], Mapping[str, Any]]


def compile_qualification_environments(
    root: Path,
    *,
    identity: Mapping[str, Any] | None = None,
    live_qualification: Mapping[str, Any] | None = None,
    live_qualification_path: Path | None = None,
    unit_contract_probe: UnitContractProbe | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if live_qualification is None:
        default_live = (
            live_qualification_path.resolve()
            if live_qualification_path is not None
            else (root / DEFAULT_LIVE_QUALIFICATION_PATH)
        )
        try:
            default_live.relative_to(root.resolve())
        except ValueError:
            live_qualification = {
                "bound_head": "",
                "bound_tree": "",
                "stages": [],
                "_path_error": "evidence_path_escape",
            }
        else:
            if default_live.is_file():
                live_qualification = read_json(default_live)
    observed = dict(identity) if identity is not None else inspect_worktree_identity(root)
    sha = str(observed.get("sha") or "")
    tree = str(observed.get("tree") or "")
    dirty = bool(observed.get("dirty"))
    identity_ok = bool(observed.get("ok")) and len(sha) == 40 and len(tree) == 40 and not dirty
    environments: list[dict[str, Any]] = []
    missing: list[str] = []

    unit_result = (
        dict(unit_contract_probe())
        if unit_contract_probe is not None
        else _default_unit_contract(root)
    )
    environments.append(
        _environment_row(
            "deterministic_unit_and_contract",
            identity_ok and str(unit_result.get("outcome")) == "PASSED",
            unit_result,
            sha,
            tree,
        )
    )
    if environments[-1]["outcome"] != "PASSED":
        missing.append("deterministic_unit_and_contract")

    environments.append(
        _environment_row(
            "isolated_real_git_worktree_journey",
            identity_ok,
            {
                "worktree": str(root),
                "dirty": dirty,
                "identity_ok": identity_ok,
            },
            sha,
            tree,
        )
    )
    if environments[-1]["outcome"] != "PASSED":
        missing.append("isolated_real_git_worktree_journey")

    mapped = _map_live_qualification(live_qualification, sha, tree)
    for name in (
        "authorized_github_jira_sandbox_or_live",
        "local_real_integrated_journey",
        "qualified_real_worker_provider_dispatch",
        "recovery_and_restart",
        "windows_service_and_command_center",
    ):
        row = mapped[name]
        environments.append(row)
        if row["outcome"] != "PASSED":
            missing.append(name)

    remaining = list(DURATION_OR_RELEASE_ENVIRONMENTS)
    return {
        "schema_version": "1.0.0",
        "compiled_at_utc": datetime.now(UTC).isoformat(),
        "bound_head": sha.lower() if identity_ok else None,
        "bound_tree": tree.lower() if identity_ok else None,
        "dirty": dirty,
        "ok": not missing,
        "environments": environments,
        "missing": missing,
        "remaining_duration_or_release": remaining,
        "inherited_ancestor": bool(mapped.get("_ancestor")),
    }


def write_qualification_environment_report(path: Path, report: Mapping[str, Any]) -> None:
    write_json(path, dict(report))


def _default_unit_contract(root: Path) -> dict[str, Any]:
    report = evaluate_nonduration_qualification(root)
    return {
        "outcome": "PASSED" if report.get("ok") else "FAILED",
        "nonduration_ok": report.get("ok"),
        "implementation_state": report.get("implementation_state"),
        "probe": "evaluate_nonduration_qualification",
    }


def _map_live_qualification(
    live_qualification: Mapping[str, Any] | None,
    sha: str,
    tree: str,
) -> dict[str, Any]:
    failed: dict[str, Any] = {
        name: _environment_row(
            name,
            False,
            {"reason": "live_qualification_missing_or_unbound"},
            sha,
            tree,
        )
        for name in (
            "authorized_github_jira_sandbox_or_live",
            "local_real_integrated_journey",
            "qualified_real_worker_provider_dispatch",
            "recovery_and_restart",
            "windows_service_and_command_center",
        )
    }
    if live_qualification is None:
        failed["_ancestor"] = False
        return failed
    if str(live_qualification.get("_path_error") or ""):
        for name, row in failed.items():
            if name.startswith("_"):
                continue
            row["observations"] = {"reason": str(live_qualification["_path_error"])}
        failed["_ancestor"] = False
        return failed
    bound_head = str(live_qualification.get("bound_head") or "").lower()
    bound_tree = str(live_qualification.get("bound_tree") or "").lower()
    if bound_head != sha.lower() or bound_tree != tree.lower():
        for name, row in failed.items():
            if name.startswith("_"):
                continue
            row["observations"] = {
                "reason": "ancestor_or_different_head_receipt",
                "receipt_head": bound_head,
                "receipt_tree": bound_tree,
            }
        failed["_ancestor"] = True
        return failed
    stages = {
        str(item.get("stage_id")): item
        for item in live_qualification.get("stages", [])
        if isinstance(item, dict)
    }
    mapped: dict[str, Any] = {"_ancestor": False}
    github = stages.get("github_jira_governance") or {}
    cursor = stages.get("cursor_cli_provider_dispatch") or {}
    windows = stages.get("windows_service_foreground") or {}
    command_center = stages.get("command_center_truth") or {}
    windows_observations = windows.get("observations") or {}
    recovery_exit = windows_observations.get("recovery_exit_code")
    recovery_ok = str(windows.get("outcome")) == "PASSED" and recovery_exit == 0
    mapped["authorized_github_jira_sandbox_or_live"] = _environment_row(
        "authorized_github_jira_sandbox_or_live",
        str(github.get("outcome")) == "PASSED",
        {"stage_id": "github_jira_governance", "outcome": github.get("outcome")},
        sha,
        tree,
    )
    mapped["qualified_real_worker_provider_dispatch"] = _environment_row(
        "qualified_real_worker_provider_dispatch",
        str(cursor.get("outcome")) == "PASSED",
        {"stage_id": "cursor_cli_provider_dispatch", "outcome": cursor.get("outcome")},
        sha,
        tree,
    )
    mapped["windows_service_and_command_center"] = _environment_row(
        "windows_service_and_command_center",
        str(windows.get("outcome")) == "PASSED" and str(command_center.get("outcome")) == "PASSED",
        {
            "windows_service_foreground": windows.get("outcome"),
            "command_center_truth": command_center.get("outcome"),
        },
        sha,
        tree,
    )
    mapped["recovery_and_restart"] = _environment_row(
        "recovery_and_restart",
        recovery_ok,
        {
            "recovery_exit_code": (windows.get("observations") or {}).get("recovery_exit_code"),
            "windows_outcome": windows.get("outcome"),
        },
        sha,
        tree,
    )
    all_pp384 = all(
        str((stages.get(stage_id) or {}).get("outcome")) == "PASSED"
        for stage_id in REQUIRED_PP384_STAGES
    )
    mapped["local_real_integrated_journey"] = _environment_row(
        "local_real_integrated_journey",
        all_pp384,
        {
            "pp384_stages": {
                stage_id: (stages.get(stage_id) or {}).get("outcome")
                for stage_id in REQUIRED_PP384_STAGES
            }
        },
        sha,
        tree,
    )
    return mapped


def _environment_row(
    name: str,
    passed: bool,
    observations: Mapping[str, Any],
    sha: str,
    tree: str,
) -> dict[str, Any]:
    return {
        "environment": name,
        "outcome": "PASSED" if passed else "FAILED",
        "bound_head": sha.lower() if sha else None,
        "bound_tree": tree.lower() if tree else None,
        "observations": dict(observations),
    }
