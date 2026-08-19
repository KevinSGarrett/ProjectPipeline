from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from project_pipeline.domain.assurance import (
    DeliveryGateDecision,
    DeliveryGateState,
    ProgressDelta,
    assurance_identifier,
)

_COMPLETE_IMPLEMENTATION_STATES = {
    "IMPLEMENTED",
    "MOCK_VERIFIED",
    "LIVE_VERIFIED",
    "BLOCKED_EXTERNAL",
}
_IMPLEMENTATION_CLAIM_LABELS = {"implemented", "reconciled", "verified", "done"}
_OBSERVATION_ALIGNED_STATES = {
    "in progress": "IN_PROGRESS",
    "to do": "BACKLOG",
}
_ISSUE_ROOTS = {"tasks", "stories", "bugs", "subtasks"}
_GENERATED_PREFIXES = (
    "docs/generated/",
    "jira/indexes/",
    "jira/relationships/",
    "jira/reports/",
    "jira/remote_sync/",
    "plans/_indexes/",
    "plans/_line_numbered/",
    "plans/_traceability/",
    "schemas/",
)
_GENERATED_FILES = {
    "FILE_MANIFEST.sha256",
    "PROJECT_MANIFEST.json",
    "evidence/EVIDENCE_SUMMARY.json",
    "instructions/INSTRUCTION_MANIFEST.json",
    "jira/BOARD_MANIFEST.json",
    "plans/01_requirements/REQUIREMENT_CATALOG_STATUS.md",
    "tests/TEST_CATALOG.json",
}
_IMPLEMENTATION_PREFIXES = (
    "src/",
    "apps/",
    "database/",
    "infrastructure/",
)


def calculate_progress_delta(
    *,
    before: Mapping[str, int],
    after: Mapping[str, int],
    activity_units: int,
    administrative_units: int,
    noncritical_administrative_units: int | None = None,
) -> ProgressDelta:
    if activity_units < 0 or administrative_units < 0:
        raise ValueError("work units cannot be negative")
    if administrative_units > activity_units:
        raise ValueError("administrative units cannot exceed activity units")
    noncritical = (
        administrative_units
        if noncritical_administrative_units is None
        else noncritical_administrative_units
    )
    if not 0 <= noncritical <= administrative_units:
        raise ValueError("noncritical administration must be within total administration")
    implemented = after.get("implemented_requirements", 0) - before.get(
        "implemented_requirements", 0
    )
    criteria = after.get("verified_criteria", 0) - before.get("verified_criteria", 0)
    blocker_reduction = before.get("blockers", 0) - after.get("blockers", 0)
    failure_reduction = before.get("failures", 0) - after.get("failures", 0)
    evidence = after.get("verified_evidence", 0) - before.get("verified_evidence", 0)
    tested = after.get("tested_implementations", 0) - before.get("tested_implementations", 0)
    integrated = after.get("integrated_changes", 0) - before.get("integrated_changes", 0)
    positive = tuple(
        max(value, 0)
        for value in (
            implemented,
            criteria,
            blocker_reduction,
            failure_reduction,
            evidence,
            tested,
            integrated,
        )
    )
    progress_units = sum(positive)
    ratio = (administrative_units * 1000) // activity_units if activity_units else 0
    noncritical_ratio = (noncritical * 1000) // activity_units if activity_units else 0
    identity = tuple(
        str(value)
        for value in (
            implemented,
            criteria,
            blocker_reduction,
            failure_reduction,
            evidence,
            tested,
            integrated,
            activity_units,
            administrative_units,
            noncritical,
        )
    )
    return ProgressDelta(
        delta_id=assurance_identifier("PDELTA", *identity),
        implemented_requirement_delta=implemented,
        verified_criterion_delta=criteria,
        blocker_reduction_delta=blocker_reduction,
        failure_reduction_delta=failure_reduction,
        verified_evidence_delta=evidence,
        tested_implementation_delta=tested,
        integrated_change_delta=integrated,
        progress_units=progress_units,
        activity_units=activity_units,
        administrative_units=administrative_units,
        administrative_ratio_milli=ratio,
        noncritical_administrative_units=noncritical,
        noncritical_administrative_ratio_milli=noncritical_ratio,
        meaningful_progress=progress_units > 0,
    )


def _run_git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git failure"
        raise ValueError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout


def _json_at_ref(root: Path, ref: str, path: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{path}"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return None
    loaded = json.loads(result.stdout)
    if not isinstance(loaded, dict):
        raise ValueError(f"expected JSON object at {ref}:{path}")
    return loaded


def _json_lines_at_ref(root: Path, ref: str, path: str) -> dict[str, dict[str, Any]]:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{path}"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"expected JSON objects in {ref}:{path}")
        identifier = str(item.get("requirement_id") or item.get("evidence_id") or "")
        if identifier:
            rows[identifier] = item
    return rows


def _is_issue_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return len(parts) == 3 and parts[0] == "jira" and parts[1] in _ISSUE_ROOTS


def _is_generated_path(path: str) -> bool:
    return path in _GENERATED_FILES or path.startswith(_GENERATED_PREFIXES)


def _normalized_issue(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    normalized: dict[str, Any] = json.loads(json.dumps(value))
    for key in (
        "state",
        "implementation_state",
        "last_observed_remote_state",
        "completion_evidence",
        "labels",
    ):
        normalized.pop(key, None)
    for criterion in normalized.get("acceptance_criteria", ()):
        if isinstance(criterion, dict) and isinstance(criterion.get("verification"), dict):
            criterion["verification"].pop("status", None)
    return normalized


def _evidence_backed(issue: Mapping[str, Any] | None) -> bool:
    if issue is None:
        return False
    if issue.get("implementation_state") not in _COMPLETE_IMPLEMENTATION_STATES:
        return False
    if not issue.get("completion_evidence"):
        return False
    criteria = issue.get("acceptance_criteria", ())
    return bool(criteria) and all(
        isinstance(item, dict)
        and isinstance(item.get("verification"), dict)
        and item["verification"].get("status") == "VERIFIED"
        for item in criteria
    )


def _verification_statuses(issue: Mapping[str, Any] | None) -> tuple[Any, ...]:
    if issue is None:
        return ()
    return tuple(
        item.get("verification", {}).get("status")
        for item in issue.get("acceptance_criteria", ())
        if isinstance(item, dict) and isinstance(item.get("verification"), dict)
    )


def _lifecycle_changed(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> bool:
    if before is None or after is None:
        return False
    tracked = ("state", "implementation_state", "completion_evidence", "labels")
    if any(before.get(key) != after.get(key) for key in tracked):
        return True
    return _verification_statuses(before) != _verification_statuses(after)


def _remote_observation_alignment_only(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> bool:
    if before is None or after is None:
        return False
    if before.get("implementation_state") != after.get("implementation_state"):
        return False
    if before.get("completion_evidence") != after.get("completion_evidence"):
        return False
    if _verification_statuses(before) != _verification_statuses(after):
        return False
    observed = after.get("last_observed_remote_state")
    if not isinstance(observed, dict):
        return False
    observed_status = str(observed.get("status_name") or "").strip().lower()
    aligned_state = _OBSERVATION_ALIGNED_STATES.get(observed_status)
    if aligned_state is None or str(after.get("state") or "") != aligned_state:
        return False
    if not str(after.get("remote_jira_key") or "").strip():
        return False
    added_labels = {str(item) for item in after.get("labels", ())} - {
        str(item) for item in before.get("labels", ())
    }
    if added_labels & _IMPLEMENTATION_CLAIM_LABELS:
        return False
    return before.get("state") != after.get("state") or before.get("labels") != after.get("labels")


def _requirement_progress(root: Path, base_ref: str, head_ref: str) -> int:
    path = "plans/_traceability/requirements.jsonl"
    before = _json_lines_at_ref(root, base_ref, path)
    after = _json_lines_at_ref(root, head_ref, path)
    return sum(
        item.get("implementation_state") in _COMPLETE_IMPLEMENTATION_STATES
        and before.get(identifier, {}).get("implementation_state")
        not in _COMPLETE_IMPLEMENTATION_STATES
        for identifier, item in after.items()
    )


def _evidence_progress(root: Path, base_ref: str, head_ref: str) -> int:
    path = "evidence/EVIDENCE_LEDGER.jsonl"
    before = _json_lines_at_ref(root, base_ref, path)
    after = _json_lines_at_ref(root, head_ref, path)
    return sum(
        identifier not in before
        and item.get("result") == "PASS"
        and item.get("verification_status") == "VERIFIED"
        for identifier, item in after.items()
    )


def _verified_criteria(issue: Mapping[str, Any] | None) -> int:
    if issue is None:
        return 0
    return sum(
        isinstance(item, dict)
        and isinstance(item.get("verification"), dict)
        and item["verification"].get("status") == "VERIFIED"
        for item in issue.get("acceptance_criteria", ())
    )


def _reconciliation_compatible(issues: Sequence[Mapping[str, Any]]) -> bool:
    if not issues:
        return False
    parents = {str(item.get("parent") or "") for item in issues}
    if len(parents) == 1 and "" not in parents:
        return True
    capabilities = {str(item.get("owner_required_capability") or "") for item in issues}
    ignored_labels = {"implemented", "reconciled", "pass-15", "pass-16"}
    common_labels: set[str] | None = None
    for issue in issues:
        labels = {str(item) for item in issue.get("labels", ())} - ignored_labels
        common_labels = labels if common_labels is None else common_labels & labels
    return len(capabilities) == 1 and "" not in capabilities and bool(common_labels)


def _catalog_test_paths(root: Path, head_ref: str) -> dict[str, str]:
    catalog = _json_at_ref(root, head_ref, "tests/TEST_CATALOG.json") or {}
    return {
        str(item["test_id"]): str(item["path"])
        for item in catalog.get("tests", ())
        if isinstance(item, dict) and item.get("test_id") and item.get("path")
    }


def _issue_bound_material_slice(
    root: Path,
    head_ref: str,
    changed: Sequence[str],
    transition_paths: Sequence[str],
    issue_pairs: Mapping[str, tuple[dict[str, Any] | None, dict[str, Any] | None]],
) -> bool:
    if not transition_paths:
        return False
    changed_set = set(changed)
    test_paths = _catalog_test_paths(root, head_ref)
    for path in transition_paths:
        issue = issue_pairs[path][1]
        if issue is None:
            return False
        artifacts = {str(item) for item in issue.get("expected_implementation_artifacts", ())}
        required_tests = {
            test_paths[str(item)]
            for item in issue.get("required_tests", ())
            if str(item) in test_paths
        }
        if not artifacts.intersection(changed_set) or not required_tests.intersection(changed_set):
            return False
    return True


def _material_governance_slice(changed: Sequence[str], *, has_lifecycle: bool) -> bool:
    changed_set = set(changed)
    governed_change = any(
        path.startswith(("instructions/", "config/", ".github/workflows/")) for path in changed
    )
    return (
        not has_lifecycle
        and governed_change
        and "instructions/INSTRUCTION_MANIFEST.json" in changed_set
        and "tests/test_instruction_system.py" in changed_set
    )


def evaluate_delivery_gate(
    root: Path,
    *,
    base_ref: str,
    head_ref: str = "HEAD",
    minimum_reconciliation_batch_items: int = 3,
    maximum_noncritical_administrative_ratio_milli: int = 100,
) -> DeliveryGateDecision:
    if minimum_reconciliation_batch_items < 2:
        raise ValueError("reconciliation batching must require at least two items")
    if not 0 <= maximum_noncritical_administrative_ratio_milli <= 1000:
        raise ValueError("administrative ratio limit must be between zero and 1000")
    changed = tuple(
        sorted(
            path.strip().replace("\\", "/")
            for path in _run_git(
                root, "diff", "--name-only", "--diff-filter=ACMR", base_ref, head_ref
            ).splitlines()
            if path.strip()
        )
    )
    issue_paths = tuple(path for path in changed if _is_issue_path(path))
    issue_pairs = {
        path: (_json_at_ref(root, base_ref, path), _json_at_ref(root, head_ref, path))
        for path in issue_paths
    }
    lifecycle_only = tuple(
        path
        for path, (before, after) in issue_pairs.items()
        if before != after and _normalized_issue(before) == _normalized_issue(after)
    )
    lifecycle_transition_paths = tuple(
        path
        for path, (before, after) in issue_pairs.items()
        if _lifecycle_changed(before, after)
        and not _remote_observation_alignment_only(before, after)
    )
    task_ids = tuple(
        sorted(
            str(after.get("local_id"))
            for _, after in issue_pairs.values()
            if after and after.get("local_id")
        )
    )
    lifecycle_ids: list[str] = []
    for path in lifecycle_transition_paths:
        after = issue_pairs[path][1]
        if after is not None and after.get("local_id"):
            lifecycle_ids.append(str(after["local_id"]))
    lifecycle_task_ids = tuple(sorted(lifecycle_ids))
    nongenerated = tuple(path for path in changed if not _is_generated_path(path))
    non_issue_nongenerated = tuple(path for path in nongenerated if not _is_issue_path(path))
    lifecycle_only_delivery = (
        bool(lifecycle_only)
        and not non_issue_nongenerated
        and len(lifecycle_only) == len(issue_paths)
    )
    reconciliation_issue_list: list[Mapping[str, Any]] = []
    for path in lifecycle_only:
        issue = issue_pairs[path][1]
        if issue is not None:
            reconciliation_issue_list.append(issue)
    reconciliation_issues = tuple(reconciliation_issue_list)
    reconciliation_batch = (
        lifecycle_only_delivery
        and len(lifecycle_task_ids) >= minimum_reconciliation_batch_items
        and all(_evidence_backed(issue_pairs[path][1]) for path in lifecycle_only)
        and _reconciliation_compatible(reconciliation_issues)
    )
    implementation_files = sum(path.startswith(_IMPLEMENTATION_PREFIXES) for path in changed)
    test_files = sum(path.startswith("tests/") for path in changed)
    requirement_units = _requirement_progress(root, base_ref, head_ref)
    evidence_units = _evidence_progress(root, base_ref, head_ref)
    generic_tested_implementation = implementation_files > 0 and test_files > 0
    issue_bound_material = _issue_bound_material_slice(
        root,
        head_ref,
        changed,
        lifecycle_transition_paths,
        issue_pairs,
    )
    material_governance = _material_governance_slice(
        changed, has_lifecycle=bool(lifecycle_task_ids)
    )
    catalog_backed_implementation = requirement_units > 0 and generic_tested_implementation
    material_implementation_slice = (
        issue_bound_material
        if lifecycle_task_ids
        else generic_tested_implementation or material_governance
    )
    before_criteria = sum(_verified_criteria(pair[0]) for pair in issue_pairs.values())
    after_criteria = sum(_verified_criteria(pair[1]) for pair in issue_pairs.values())
    before_blockers = sum(
        len(pair[0].get("blockers", ())) for pair in issue_pairs.values() if pair[0]
    )
    after_blockers = sum(
        len(pair[1].get("blockers", ())) for pair in issue_pairs.values() if pair[1]
    )
    before_failures = sum(
        pair[0].get("state") == "FAILED" for pair in issue_pairs.values() if pair[0]
    )
    after_failures = sum(
        pair[1].get("state") == "FAILED" for pair in issue_pairs.values() if pair[1]
    )
    administrative_units = sum(_is_generated_path(path) for path in changed) + len(
        lifecycle_transition_paths
    )
    noncritical_administrative_units = len(lifecycle_transition_paths)
    activity_units = len(changed)
    progress_delta = calculate_progress_delta(
        before={
            "implemented_requirements": 0,
            "verified_criteria": before_criteria,
            "blockers": before_blockers,
            "failures": before_failures,
            "verified_evidence": 0,
            "tested_implementations": 0,
            "integrated_changes": 0,
        },
        after={
            "implemented_requirements": requirement_units,
            "verified_criteria": after_criteria,
            "blockers": after_blockers,
            "failures": after_failures,
            "verified_evidence": evidence_units,
            "tested_implementations": int(material_implementation_slice),
            "integrated_changes": 0,
        },
        activity_units=activity_units,
        administrative_units=administrative_units,
        noncritical_administrative_units=noncritical_administrative_units,
    )
    objective_units = progress_delta.progress_units
    ratio = progress_delta.administrative_ratio_milli
    reasons: list[str] = []
    state = DeliveryGateState.PASS
    if not changed:
        state = DeliveryGateState.BLOCKED
        reasons.append("delivery slice has no changed files")
    elif (
        lifecycle_task_ids
        and not reconciliation_batch
        and not material_implementation_slice
        and not catalog_backed_implementation
    ):
        state = DeliveryGateState.BLOCKED
        reasons.append(
            "lifecycle transitions require the issue's own declared implementation artifact and cataloged required test; unrelated churn is not progress, otherwise reconcile at least the evidence-backed batch minimum"
        )
    elif reconciliation_batch:
        reasons.append(
            f"evidence-backed reconciliation batch contains {len(lifecycle_task_ids)} compatible items"
        )
    elif progress_delta.meaningful_progress:
        reasons.append(
            "objective Progress Delta records implementation, acceptance, blocker, failure, or evidence advancement"
        )
    elif (
        not lifecycle_task_ids
        and non_issue_nongenerated
        and all(
            path.startswith(("docs/", "README", "CONTRIBUTING")) for path in non_issue_nongenerated
        )
    ):
        reasons.append("bounded documentation-only fast path")
    else:
        state = DeliveryGateState.BLOCKED
        reasons.append("slice does not contain an objective progress unit")
    if (
        progress_delta.noncritical_administrative_ratio_milli
        > maximum_noncritical_administrative_ratio_milli
        and not progress_delta.meaningful_progress
        and state is DeliveryGateState.PASS
    ):
        state = DeliveryGateState.BLOCKED
        reasons.append("noncritical administrative activity exceeds the delivery budget")
    decision_parts: Sequence[str] = (
        base_ref,
        head_ref,
        *changed,
        state.value,
        str(objective_units),
    )
    return DeliveryGateDecision(
        decision_id=assurance_identifier("DELIVERY", *decision_parts),
        state=state,
        base_ref=base_ref,
        head_ref=head_ref,
        task_ids=task_ids,
        changed_paths=changed,
        lifecycle_only_task_ids=lifecycle_task_ids,
        objective_progress_units=objective_units,
        activity_units=activity_units,
        administrative_units=min(administrative_units, activity_units),
        administrative_ratio_milli=ratio,
        noncritical_administrative_units=min(noncritical_administrative_units, activity_units),
        noncritical_administrative_ratio_milli=progress_delta.noncritical_administrative_ratio_milli,
        reconciliation_batch=reconciliation_batch,
        reasons=tuple(reasons),
    )


def load_delivery_policy(root: Path) -> dict[str, Any]:
    policy = json.loads((root / "config" / "assurance_policy.json").read_text(encoding="utf-8"))
    delivery = policy.get("delivery_progress")
    if not isinstance(delivery, dict):
        raise ValueError("assurance policy requires delivery_progress object")
    return delivery
