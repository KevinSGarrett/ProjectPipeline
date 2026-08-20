"""Content-addressed substantive acceptance-unit ledger validation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import model_validator

from project_pipeline.assurance.policy import CycleWorkloadPolicy
from project_pipeline.domain.base import DomainModel
from project_pipeline.io import read_json

ZERO_CREDIT_CATEGORIES = frozenset(
    {
        "bookkeeping",
        "branch",
        "checksum",
        "cleanup",
        "commit",
        "dependency_install",
        "generated_projection",
        "handoff_prose",
        "heartbeat",
        "jira_comment",
        "jira_transition",
        "lifecycle_only_reconciliation",
        "manifest",
        "micro_split",
        "placeholder",
        "pr",
        "repeated_validation",
        "timer_start",
        "worktree",
    }
)

REQUIRED_UNIT_FIELDS = (
    "unit_id",
    "acceptance_boundary",
    "requirement_id",
    "criterion_id",
    "falsifier",
    "before_behavior",
    "after_behavior",
    "production_paths",
    "tests",
    "integrated_sha",
    "integrated_tree",
    "rollback_boundary",
    "deduplication_identity",
    "weight",
    "counts_as_substantive",
)


class CycleWorkloadFinding(DomainModel):
    code: str
    message: str


class CycleWorkloadDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    baseline_id: str
    base_sha: str
    head_sha: str
    head_tree: str
    distinct_units: int
    weighted_score: int
    minimum_units: int
    minimum_score: int
    administrative_credit: Literal[0] = 0
    endgame_saturation: bool = False
    accepted: bool
    findings: tuple[CycleWorkloadFinding, ...] = ()


class RequirementMovement(DomainModel):
    requirement_id: str
    before: str
    after: str

    @model_validator(mode="after")
    def reject_noop(self) -> RequirementMovement:
        if self.before == self.after:
            raise ValueError(f"no-op requirement movement: {self.requirement_id}")
        return self


def load_cycle_workload_policy(root: Path) -> CycleWorkloadPolicy:
    policy = read_json(root / "config" / "assurance_policy.json")
    payload = policy.get("cycle_workload")
    if not isinstance(payload, dict):
        raise ValueError("assurance policy requires cycle_workload object")
    return CycleWorkloadPolicy.model_validate(payload)


def sha256_canonical(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_show(root: Path, spec: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), "show", spec],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError(f"unable to read git object: {spec}")
    return result.stdout


def _git_rev_parse(root: Path, spec: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", spec],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"unable to resolve git revision: {spec}")
    return result.stdout.strip()


def catalog_implementation_states(document: Mapping[str, Any] | Sequence[Any]) -> dict[str, str]:
    requirements: Any = document
    if isinstance(document, Mapping) and "requirements" in document:
        requirements = document["requirements"]
    states: dict[str, str] = {}
    if isinstance(requirements, Mapping):
        for requirement_id, item in requirements.items():
            if isinstance(item, Mapping):
                states[str(requirement_id)] = str(item.get("implementation_state") or "UNKNOWN")
            else:
                states[str(requirement_id)] = str(item)
        return states
    if isinstance(requirements, Sequence) and not isinstance(requirements, (str, bytes)):
        for item in requirements:
            if not isinstance(item, Mapping):
                continue
            requirement_id = str(item.get("requirement_id") or "")
            if requirement_id:
                states[requirement_id] = str(item.get("implementation_state") or "UNKNOWN")
        return states
    raise ValueError("requirements catalog is not an object or list")


def derive_requirement_movements(
    root: Path, *, base_ref: str, head_ref: str
) -> tuple[RequirementMovement, ...]:
    base = catalog_implementation_states(
        json.loads(_git_show(root, f"{base_ref}:plans/_traceability/requirements_by_id.json"))
    )
    head = catalog_implementation_states(
        json.loads(_git_show(root, f"{head_ref}:plans/_traceability/requirements_by_id.json"))
    )
    movements: list[RequirementMovement] = []
    for requirement_id in sorted(set(base) | set(head)):
        before = base.get(requirement_id, "ABSENT")
        after = head.get(requirement_id, "ABSENT")
        if before == after:
            continue
        movements.append(
            RequirementMovement(requirement_id=requirement_id, before=before, after=after)
        )
    return tuple(movements)


def validate_requirement_movement_ledger(
    ledger: Mapping[str, Any] | Sequence[Any],
    expected: Sequence[RequirementMovement],
) -> list[CycleWorkloadFinding]:
    findings: list[CycleWorkloadFinding] = []
    rows = ledger.get("rows") if isinstance(ledger, Mapping) else ledger
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return [
            CycleWorkloadFinding(
                code="MOVEMENT_LEDGER_INVALID",
                message="requirement movement ledger is not a row list",
            )
        ]
    observed: dict[str, tuple[str, str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            findings.append(
                CycleWorkloadFinding(
                    code="MOVEMENT_ROW_INVALID",
                    message="requirement movement row is not an object",
                )
            )
            continue
        requirement_id = str(row.get("requirement_id") or row.get("id") or "")
        before = str(row.get("before") or row.get("before_state") or "")
        after = str(row.get("after") or row.get("after_state") or "")
        if not requirement_id or not before or not after:
            findings.append(
                CycleWorkloadFinding(
                    code="MOVEMENT_ROW_INCOMPLETE",
                    message="requirement movement row is missing id/before/after",
                )
            )
            continue
        if before == after:
            findings.append(
                CycleWorkloadFinding(
                    code="MOVEMENT_NOOP",
                    message=f"no-op requirement movement: {requirement_id}",
                )
            )
            continue
        if requirement_id in observed:
            findings.append(
                CycleWorkloadFinding(
                    code="MOVEMENT_DUPLICATE",
                    message=f"duplicate requirement movement: {requirement_id}",
                )
            )
            continue
        observed[requirement_id] = (before, after)

    expected_map = {item.requirement_id: (item.before, item.after) for item in expected}
    for requirement_id, pair in expected_map.items():
        if requirement_id not in observed:
            findings.append(
                CycleWorkloadFinding(
                    code="MOVEMENT_MISSING",
                    message=f"missing requirement movement: {requirement_id}",
                )
            )
            continue
        if observed[requirement_id] != pair:
            observed_before, observed_after = observed[requirement_id]
            if observed_before != pair[0]:
                findings.append(
                    CycleWorkloadFinding(
                        code="MOVEMENT_WRONG_BEFORE",
                        message=f"wrong-before requirement movement: {requirement_id}",
                    )
                )
            if observed_after != pair[1]:
                findings.append(
                    CycleWorkloadFinding(
                        code="MOVEMENT_WRONG_AFTER",
                        message=f"wrong-after requirement movement: {requirement_id}",
                    )
                )
    for requirement_id in observed:
        if requirement_id not in expected_map:
            findings.append(
                CycleWorkloadFinding(
                    code="MOVEMENT_EXTRA",
                    message=f"extra requirement movement: {requirement_id}",
                )
            )
    return findings


def _unit_rows(ledger: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    rows = ledger.get("units") or ledger.get("rows") or []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("cycle workload ledger units must be a list")
    return tuple(item for item in rows if isinstance(item, Mapping))


def evaluate_cycle_workload(
    *,
    root: Path,
    policy: CycleWorkloadPolicy | None = None,
    ledger: Mapping[str, Any] | None = None,
    requirement_ledger: Mapping[str, Any] | Sequence[Any] | None = None,
    base_ref: str | None = None,
    head_ref: str | None = None,
) -> CycleWorkloadDecision:
    policy = policy or load_cycle_workload_policy(root)
    findings: list[CycleWorkloadFinding] = []
    supplied_ledger = ledger
    ledger = dict(ledger or {})
    base_ref = str(base_ref or ledger.get("base_sha") or "")
    head_ref = str(head_ref or ledger.get("head_sha") or "")
    try:
        head_sha = _git_rev_parse(root, head_ref) if head_ref else ""
        head_tree = _git_rev_parse(root, f"{head_ref}^{{tree}}") if head_ref else ""
        base_sha = _git_rev_parse(root, base_ref) if base_ref else ""
    except ValueError as error:
        findings.append(CycleWorkloadFinding(code="GIT_IDENTITY", message=str(error)))
        head_sha = str(ledger.get("head_sha") or "")
        head_tree = str(ledger.get("head_tree") or "")
        base_sha = str(ledger.get("base_sha") or "")

    declared_base = str(ledger.get("base_sha") or "")
    declared_head = str(ledger.get("head_sha") or "")
    declared_tree = str(ledger.get("head_tree") or "")
    if declared_base and base_sha and declared_base != base_sha:
        findings.append(
            CycleWorkloadFinding(code="WRONG_BASE", message="ledger base_sha does not match git")
        )
    if declared_head and head_sha and declared_head != head_sha:
        findings.append(
            CycleWorkloadFinding(code="WRONG_HEAD", message="ledger head_sha does not match git")
        )
    if declared_tree and head_tree and declared_tree != head_tree:
        findings.append(
            CycleWorkloadFinding(
                code="CONTRADICTORY_TREE",
                message="ledger head_tree does not match git",
            )
        )
    if declared_head and head_sha and declared_head != head_sha:
        findings.append(
            CycleWorkloadFinding(code="STALE_HEAD", message="ledger head is stale relative to git")
        )

    units = _unit_rows(ledger) if supplied_ledger else ()
    unit_ids: set[str] = set()
    rollback_ids: set[str] = set()
    fingerprints: set[str] = set()
    score = 0
    counted = 0
    for unit in units:
        missing = [field for field in REQUIRED_UNIT_FIELDS if not unit.get(field)]
        if missing:
            findings.append(
                CycleWorkloadFinding(
                    code="INCOMPLETE_EVIDENCE",
                    message=f"unit missing required fields: {', '.join(missing)}",
                )
            )
            continue
        unit_id = str(unit["unit_id"])
        rollback = str(unit["rollback_boundary"])
        dedup = str(unit["deduplication_identity"])
        fingerprint = sha256_canonical(
            {
                "acceptance_boundary": unit.get("acceptance_boundary"),
                "deduplication_identity": dedup,
                "rollback_boundary": rollback,
            }
        )
        if unit_id in unit_ids:
            findings.append(
                CycleWorkloadFinding(code="DUPLICATE_UNIT", message=f"duplicate unit id: {unit_id}")
            )
        unit_ids.add(unit_id)
        if rollback in rollback_ids or fingerprint in fingerprints:
            findings.append(
                CycleWorkloadFinding(
                    code="IDENTICAL_ROLLBACK",
                    message=f"identical rollback/dedup boundary: {unit_id}",
                )
            )
        rollback_ids.add(rollback)
        fingerprints.add(fingerprint)
        category = str(unit.get("category") or "")
        if category in ZERO_CREDIT_CATEGORIES or unit.get("counts_as_substantive") is False:
            if unit.get("counts_as_substantive") is True:
                code = (
                    "DEPENDENCY_INSTALL_CREDIT"
                    if category == "dependency_install"
                    else "ADMINISTRATIVE_CREDIT"
                )
                findings.append(
                    CycleWorkloadFinding(
                        code=code,
                        message=f"zero-credit category counted as substantive: {unit_id}",
                    )
                )
            continue
        try:
            weight = int(unit["weight"])
        except (TypeError, ValueError):
            findings.append(
                CycleWorkloadFinding(code="INVALID_WEIGHT", message=f"invalid weight: {unit_id}")
            )
            continue
        if weight < 1 or weight > policy.maximum_unit_weight:
            findings.append(
                CycleWorkloadFinding(
                    code="INVALID_WEIGHT",
                    message=f"weight {weight} exceeds maximum {policy.maximum_unit_weight}: {unit_id}",
                )
            )
            continue
        if unit.get("integrated_sha") and head_sha and str(unit["integrated_sha"]) != head_sha:
            findings.append(
                CycleWorkloadFinding(
                    code="UNIT_HEAD_MISMATCH",
                    message=f"unit integrated sha is not the evaluated head: {unit_id}",
                )
            )
        counted += 1
        score += weight

    if int(ledger.get("administrative_credit") or 0) != 0:
        findings.append(
            CycleWorkloadFinding(
                code="ADMINISTRATIVE_CREDIT",
                message="administrative_credit must be 0",
            )
        )
    if ledger.get("invalid_ledger_document"):
        findings.append(
            CycleWorkloadFinding(
                code="LEDGER_INVALID",
                message="cycle workload ledger must be a JSON object",
            )
        )
    if ledger.get("allow_missing_movement_ledger"):
        findings.append(
            CycleWorkloadFinding(
                code="MOVEMENT_LEDGER_BYPASS",
                message="allow_missing_movement_ledger is not a valid exemption",
            )
        )

    expected_movements: tuple[RequirementMovement, ...] = ()
    if units and (not base_sha or not head_sha):
        findings.append(
            CycleWorkloadFinding(
                code="GIT_RANGE_REQUIRED",
                message="substantive units require a resolvable base_sha and head_sha",
            )
        )
    if base_sha and head_sha:
        try:
            expected_movements = derive_requirement_movements(
                root, base_ref=base_sha, head_ref=head_sha
            )
        except ValueError as error:
            findings.append(CycleWorkloadFinding(code="MOVEMENT_DERIVATION", message=str(error)))
    if requirement_ledger is not None:
        findings.extend(
            validate_requirement_movement_ledger(requirement_ledger, expected_movements)
        )
    elif expected_movements:
        findings.append(
            CycleWorkloadFinding(
                code="MOVEMENT_LEDGER_MISSING",
                message="requirement movement ledger is required for a range with movements",
            )
        )

    below_minimum = counted < policy.minimum_units or score < policy.minimum_score
    endgame = bool(ledger.get("endgame_saturation"))
    if below_minimum and not endgame:
        findings.append(
            CycleWorkloadFinding(
                code="ENDGAME_SATURATION_REQUIRED",
                message=(
                    "weighted score/units are below the doubled high-water minimum; "
                    "endgame saturation is required"
                ),
            )
        )
    if endgame and not bool(ledger.get("completion_gate_complete")):
        findings.append(
            CycleWorkloadFinding(
                code="ENDGAME_SATURATION_INCOMPLETE",
                message="endgame saturation requires Completion Gate COMPLETE",
            )
        )

    accepted = not findings
    return CycleWorkloadDecision(
        baseline_id=policy.baseline_id,
        base_sha=base_sha,
        head_sha=head_sha,
        head_tree=head_tree,
        distinct_units=counted,
        weighted_score=score,
        minimum_units=policy.minimum_units,
        minimum_score=policy.minimum_score,
        administrative_credit=0,
        endgame_saturation=endgame,
        accepted=accepted,
        findings=tuple(findings),
    )


def evaluate_cycle_workload_from_root(
    root: Path,
    *,
    ledger_path: Path | None = None,
    requirement_ledger_path: Path | None = None,
    base_ref: str | None = None,
    head_ref: str | None = None,
) -> CycleWorkloadDecision:
    ledger: Mapping[str, Any] | None = None
    requirement_ledger: Mapping[str, Any] | Sequence[Any] | None = None
    if ledger_path is not None and ledger_path.is_file():
        payload = read_json(ledger_path)
        if isinstance(payload, dict):
            ledger = payload
        else:
            ledger = {"units": [], "invalid_ledger_document": True}
    if requirement_ledger_path is not None and requirement_ledger_path.is_file():
        payload = read_json(requirement_ledger_path)
        requirement_ledger = payload if isinstance(payload, (dict, list)) else {"rows": "invalid"}
    return evaluate_cycle_workload(
        root=root,
        ledger=ledger,
        requirement_ledger=requirement_ledger,
        base_ref=base_ref,
        head_ref=head_ref,
    )
