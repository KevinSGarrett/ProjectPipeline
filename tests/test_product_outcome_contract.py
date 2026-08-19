from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest

from project_pipeline.io import read_json, read_jsonl, write_json, write_jsonl
from project_pipeline.validation.models import ValidationReport
from project_pipeline.validation.product_model_audit import (
    audit_product_model,
    validate_independent_product_model_audit,
)
from project_pipeline.validation.product_outcome import (
    CORE_REQUIREMENT_ID,
    validate_product_outcome,
)
from project_pipeline.validation.registries import check_plan_registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def product_root(tmp_path: Path) -> Path:
    for relative in (
        "config/product_outcome.json",
        "plans/PLAN_CATALOG.json",
        "plans/_traceability/requirements.jsonl",
        "plans/_traceability/source_sections.jsonl",
        "plans/reconciliation/IMPLEMENTED_REQUIREMENT_JIRA_AUDIT.json",
        "plans/reconciliation/BROAD_SOURCE_RANGE_AUDIT.json",
        "plans/reconciliation/BROAD_SOURCE_RANGE_DECISIONS.json",
        "evidence/EVIDENCE_LEDGER.jsonl",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for directory in ("epics", "stories", "tasks"):
        source = ROOT / "jira" / directory
        target = tmp_path / "jira" / directory
        target.mkdir(parents=True, exist_ok=True)
        for path in source.glob("PP-*.json"):
            shutil.copy2(path, target / path.name)
    return tmp_path


def _rewrite_requirement(root: Path, requirement_id: str, **updates: object) -> None:
    path = root / "plans/_traceability/requirements.jsonl"
    rows = read_jsonl(path)
    for row in rows:
        if row.get("requirement_id") == requirement_id:
            row.update(updates)
            write_jsonl(path, rows)
            return
    raise AssertionError(f"missing fixture requirement: {requirement_id}")


def test_repaired_product_outcome_contract_is_fail_closed_and_valid() -> None:
    assert validate_product_outcome(ROOT) == []
    assert validate_independent_product_model_audit(ROOT) == []
    report = audit_product_model(ROOT)
    assert report["independent_of"] == "validate_product_outcome"
    assert report["resume_authorized"] is True
    assert "PP-TASK-000385" in report["genuinely_missing"]


def test_ordinary_control_selection_cannot_resume_outside_runtime_slices(
    product_root: Path,
) -> None:
    path = product_root / "config/product_outcome.json"
    contract = read_json(path)
    contract["control_selection"] = {
        "mode": "NORMAL_BACKLOG",
        "allowed_issue_ids": ["PP-TASK-000168"],
        "resume_rule": "unreviewed",
    }
    write_json(path, contract)

    errors = validate_product_outcome(product_root)
    assert "ordinary Control selection must remain product-outcome bounded" in errors
    assert "Control selection must be bounded to the six cohesive runtime slices" in errors


def test_previous_missing_outcome_and_broad_intake_coverage_fail(product_root: Path) -> None:
    requirements_path = product_root / "plans/_traceability/requirements.jsonl"
    rows = [
        row for row in read_jsonl(requirements_path) if row["requirement_id"] != CORE_REQUIREMENT_ID
    ]
    for row in rows:
        if row["requirement_id"] == "REQ-PDEF-0006":
            row["source_references"] = ["SRC-014:L000005-L000087"]
    write_jsonl(requirements_path, rows)

    errors = validate_product_outcome(product_root)
    assert any("accepted product outcome requirement is missing" in error for error in errors)
    assert any("may not claim the autonomous-loop source range" in error for error in errors)
    assert any("claimed by unrelated narrow requirement" in error for error in errors)


def test_command_center_director_chat_cannot_qualify_persistent_director(
    product_root: Path,
) -> None:
    _rewrite_requirement(
        product_root,
        "REQ-CTRL-0004",
        implementation_state="IMPLEMENTED",
        jira_ids=["PP-EPIC-000007", "PP-STORY-000065"],
    )

    errors = validate_product_outcome(product_root)
    assert any("persistent Autonomy Director must remain incomplete" in error for error in errors)


def test_independent_audit_rejects_false_complete_and_dropped_intent(
    product_root: Path,
) -> None:
    _rewrite_requirement(
        product_root,
        CORE_REQUIREMENT_ID,
        implementation_state="IMPLEMENTED",
        evidence_ids=["EVID-LOCAL-RUNTIME"],
    )
    contract_path = product_root / "config/product_outcome.json"
    contract = read_json(contract_path)
    del contract["user_intent_contracts"]["SRC-003-SEC-001"]
    write_json(contract_path, contract)
    task_path = product_root / "jira/tasks/PP-TASK-000385.json"
    task = read_json(task_path)
    task["implementation_state"] = "IMPLEMENTED"
    write_json(task_path, task)

    errors = validate_independent_product_model_audit(product_root)
    assert any("ten explicit user-intent mappings" in error for error in errors)
    assert any("core outcome cannot be implemented" in error for error in errors)
    assert any("PP-TASK-000385 cannot be complete" in error for error in errors)
    assert validate_product_outcome is not audit_product_model


def test_user_intent_context_cannot_silently_remove_operator_outcome(
    product_root: Path,
) -> None:
    sections_path = product_root / "plans/_traceability/source_sections.jsonl"
    sections = read_jsonl(sections_path)
    target = next(row for row in sections if row["section_id"] == "SRC-014-SEC-001")
    target["disposition"] = "USER_INTENT_CONTEXT"
    target["requirement_ids"] = []
    write_jsonl(sections_path, sections)

    errors = validate_product_outcome(product_root)
    assert any("may not remain silently classified" in error for error in errors)
    assert any("SRC-014-SEC-001" in error for error in errors)


def test_outcome_requires_cohesive_epic_and_local_real_journey(product_root: Path) -> None:
    (product_root / "jira/epics/PP-EPIC-000036.json").unlink()
    journey_path = product_root / "jira/tasks/PP-TASK-000383.json"
    journey = read_json(journey_path)
    journey["description"] = "Component-only deterministic test collection."
    write_json(journey_path, journey)

    errors = validate_product_outcome(product_root)
    assert "cohesive autonomous-runtime implementation epic is missing" in errors
    assert "a cohesive local-real autonomous qualification journey is required" in errors


def test_dangling_plan_and_control_selection_references_fail_closed(product_root: Path) -> None:
    contract_path = product_root / "config/product_outcome.json"
    contract = read_json(contract_path)
    contract["plan_id"] = "PLAN-CTRL-999"
    contract["control_selection"]["allowed_issue_ids"] = ["PP-TASK-999999"]
    write_json(contract_path, contract)

    errors = validate_product_outcome(product_root)
    assert "product outcome contract references an unknown plan ID" in errors
    assert "Control selection references unknown issue: PP-TASK-999999" in errors


def test_non_task_control_selection_and_unknown_intent_requirement_fail_closed(
    product_root: Path,
) -> None:
    contract_path = product_root / "config/product_outcome.json"
    contract = read_json(contract_path)
    contract["control_selection"]["allowed_issue_ids"] = ["PP-EPIC-000036"]
    contract["user_intent_contracts"]["SRC-003-SEC-001"] = ["REQ-NOT-REAL-0001"]
    write_json(contract_path, contract)

    errors = validate_product_outcome(product_root)
    assert "Control selection may only include TASK work items: PP-EPIC-000036" in errors
    assert any(
        "user-intent contract references unknown requirements for SRC-003-SEC-001" in error
        for error in errors
    )


def test_qualification_ladder_must_match_canonical_contract(product_root: Path) -> None:
    contract_path = product_root / "config/product_outcome.json"
    contract = read_json(contract_path)
    contract["qualification_ladder"] = contract["qualification_ladder"][:-1]
    write_json(contract_path, contract)

    errors = validate_product_outcome(product_root)
    assert "qualification ladder must match the canonical ten-stage runtime contract" in errors


def test_local_or_mock_evidence_cannot_qualify_product_outcome(product_root: Path) -> None:
    evidence_path = product_root / "evidence/EVIDENCE_LEDGER.jsonl"
    evidence = read_jsonl(evidence_path)
    evidence.append(
        {
            "evidence_id": "EVID-LOCAL-RUNTIME",
            "environment": "local_build_environment",
            "method": "deterministic simulation",
            "result": "PASS",
            "verification_status": "VERIFIED",
        }
    )
    write_jsonl(evidence_path, evidence)
    _rewrite_requirement(
        product_root,
        CORE_REQUIREMENT_ID,
        implementation_state="IMPLEMENTED",
        evidence_ids=["EVID-LOCAL-RUNTIME"],
    )

    errors = validate_product_outcome(product_root)
    assert any("without 72-hour evidence" in error for error in errors)
    assert any("without released-state evidence" in error for error in errors)
    assert any("cannot qualify the product outcome" in error for error in errors)


def test_implemented_requirement_with_only_planned_jira_requires_finding(
    product_root: Path,
) -> None:
    requirements_path = product_root / "plans/_traceability/requirements.jsonl"
    rows = read_jsonl(requirements_path)
    fabricated = copy.deepcopy(rows[0])
    fabricated.update(
        requirement_id="REQ-PDEF-9999",
        implementation_state="IMPLEMENTED",
        jira_ids=["PP-TASK-000168"],
    )
    rows.append(fabricated)
    write_jsonl(requirements_path, rows)
    issue_path = product_root / "jira/tasks/PP-TASK-000168.json"
    issue = read_json(issue_path)
    issue["implementation_state"] = "PLANNED_ONLY"
    write_json(issue_path, issue)

    errors = validate_product_outcome(product_root)
    assert any("REQ-PDEF-9999" in error and "PLANNED_ONLY" in error for error in errors)


@pytest.mark.parametrize(
    ("plan_status", "catalog_status", "expected_code"),
    [(None, "ACTIVE", "PLAN012"), ("PLANNED", "ACTIVE", "PLAN013")],
)
def test_plan_catalog_must_match_authoritative_plan_status(
    tmp_path: Path,
    plan_status: str | None,
    catalog_status: str,
    expected_code: str,
) -> None:
    plan_id = "PLAN-TEST-001"
    relative = "plans/test/PLAN-TEST-001.md"
    plan = tmp_path / relative
    plan.parent.mkdir(parents=True)
    lines = [f"# {plan_id} Test"]
    if plan_status is not None:
        lines.extend(["", f"- **Status:** `{plan_status}`"])
    lines.extend(["", f"## {plan_id}:SEC-01 Contract", "", "Behavior."])
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(
        tmp_path / "plans/PLAN_CATALOG.json",
        {
            "plans": [
                {
                    "plan_id": plan_id,
                    "path": relative,
                    "status": catalog_status,
                    "source_references": [],
                }
            ]
        },
    )
    write_json(
        tmp_path / "plans/_indexes/plan_section_index.json",
        {f"{plan_id}:SEC-01": {"plan_id": plan_id}},
    )
    numbered = tmp_path / "plans/_line_numbered/PLAN-TEST-001.lines.txt"
    numbered.parent.mkdir(parents=True)
    numbered.write_text(
        "\n".join(f"L{number:06d} | {line}" for number, line in enumerate(lines, 1)) + "\n",
        encoding="utf-8",
    )
    report = ValidationReport(project_root=str(tmp_path))

    check_plan_registry(tmp_path, report)

    assert expected_code in {finding.code for finding in report.findings}


def test_plan_heading_may_carry_authoritative_status_without_changing_section_lines(
    tmp_path: Path,
) -> None:
    plan_id = "PLAN-TEST-001"
    relative = "plans/test/PLAN-TEST-001.md"
    plan = tmp_path / relative
    plan.parent.mkdir(parents=True)
    lines = [
        f"# {plan_id} Test [Status: ACTIVE]",
        "",
        f"## {plan_id}:SEC-01 Contract",
        "",
        "Behavior.",
    ]
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(
        tmp_path / "plans/PLAN_CATALOG.json",
        {"plans": [{"plan_id": plan_id, "path": relative, "status": "ACTIVE"}]},
    )
    write_json(
        tmp_path / "plans/_indexes/plan_section_index.json",
        {f"{plan_id}:SEC-01": {"plan_id": plan_id}},
    )
    numbered = tmp_path / "plans/_line_numbered/PLAN-TEST-001.lines.txt"
    numbered.parent.mkdir(parents=True)
    numbered.write_text(
        "\n".join(f"L{number:06d} | {line}" for number, line in enumerate(lines, 1)) + "\n",
        encoding="utf-8",
    )

    report = ValidationReport(project_root=str(tmp_path))
    check_plan_registry(tmp_path, report)

    assert "PLAN012" not in {finding.code for finding in report.findings}
    assert "PLAN013" not in {finding.code for finding in report.findings}
