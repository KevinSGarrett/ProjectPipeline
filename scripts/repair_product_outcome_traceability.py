from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl, write_jsonl

CORE_REQUIREMENT_ID = "REQ-PDEF-0011"
CORE_STATEMENT = (
    "ProjectPipeline shall continuously take a project from intake through verified modeling, "
    "autonomous selection, conflict-safe parallel execution, verification, governed repository "
    "integration, Jira reconciliation, project-state recomputation, and next-work selection "
    "without requiring a human to drive each development session."
)
_SOURCE = re.compile(r"^(SRC-[0-9]{3}):L([0-9]{6})-L([0-9]{6})$")

# Independent semantic audit decisions for composite source citations. Each mapping replaces one
# over-broad citation with only the ranges that actually support the atomic requirement. An empty
# replacement removes an unrelated citation. Existing independent governing-contract citations are
# intentionally preserved.
SOURCE_REFERENCE_REPAIRS: dict[str, dict[str, list[str]]] = {
    "REQ-AGENT-0008": {"SRC-006:L000130-L000223": ["SRC-006:L000130-L000197"]},
    "REQ-AGENT-0011": {"SRC-001:L000569-L000680": ["SRC-001:L000569-L000656"]},
    "REQ-ARCH-0005": {
        "SRC-002:L001099-L001314": [
            "SRC-002:L001103-L001157",
            "SRC-002:L001300-L001314",
        ]
    },
    "REQ-ASSURE-0001": {"SRC-008:L000540-L000760": ["SRC-008:L000648-L000714"]},
    "REQ-ASSURE-0002": {"SRC-008:L000540-L000760": ["SRC-008:L000595-L000647"]},
    "REQ-ASSURE-0003": {"SRC-008:L000540-L000760": ["SRC-008:L000447-L000519"]},
    "REQ-ASSURE-0004": {"SRC-008:L000540-L000760": ["SRC-008:L000520-L000594"]},
    "REQ-BUDGET-0005": {
        "SRC-004:L000148-L000251": [
            "SRC-004:L000148-L000191",
            "SRC-004:L000228-L000251",
        ]
    },
    "REQ-BUDGET-0006": {"SRC-004:L000148-L000251": ["SRC-004:L000192-L000251"]},
    "REQ-BUDGET-0011": {"SRC-004:L000484-L000606": ["SRC-004:L000484-L000563"]},
    "REQ-BUDGET-0012": {"SRC-004:L000484-L000606": ["SRC-004:L000564-L000606"]},
    "REQ-CTRL-0007": {"SRC-003:L000752-L000875": ["SRC-003:L000752-L000789"]},
    "REQ-CTRL-0009": {
        "SRC-003:L000752-L000875": [],
        "SRC-008:L000407-L000589": [
            "SRC-008:L000407-L000446",
            "SRC-008:L000493-L000589",
        ],
    },
    "REQ-CTRL-0010": {"SRC-003:L000882-L000961": ["SRC-003:L000930-L000961"]},
    "REQ-CTRL-0012": {"SRC-005:L000604-L000735": ["SRC-005:L000649-L000735"]},
    "REQ-CTRL-0013": {"SRC-014:L000210-L000373": ["SRC-014:L000242-L000373"]},
    "REQ-CTX-0001": {"SRC-002:L001015-L001156": ["SRC-002:L001015-L001046"]},
    "REQ-CTX-0002": {
        "SRC-002:L001015-L001156": [
            "SRC-002:L001015-L001046",
            "SRC-002:L001099-L001157",
        ]
    },
    "REQ-CTX-0003": {
        "SRC-002:L001015-L001156": [
            "SRC-002:L001047-L001098",
            "SRC-017:L000009-L000071",
        ]
    },
    "REQ-CTX-0011": {"SRC-002:L001015-L001098": ["SRC-017:L000009-L000071"]},
    "REQ-INFRA-0010": {"SRC-016:L001473-L001690": ["SRC-016:L001473-L001509"]},
    "REQ-OPS-0010": {"SRC-015:L000359-L000488": ["SRC-015:L000407-L000457"]},
    "REQ-REQ-0005": {"SRC-017:L000490-L000596": ["SRC-017:L000490-L000572"]},
    "REQ-REQ-0006": {"SRC-017:L000490-L000596": ["SRC-017:L000490-L000572"]},
    "REQ-REQ-0012": {"SRC-017:L000490-L000596": ["SRC-017:L000490-L000572"]},
    "REQ-REQ-0015": {"SRC-017:L000490-L000596": ["SRC-017:L000490-L000572"]},
    "REQ-SCHED-0004": {
        "SRC-003:L000225-L000371": ["SRC-003:L000225-L000278"],
        "SRC-014:L000210-L000373": [],
    },
    "REQ-SCHED-0006": {
        "SRC-003:L000279-L000371": ["SRC-003:L000279-L000335"],
        "SRC-014:L000378-L000748": ["SRC-014:L000378-L000525"],
    },
    "REQ-SCHED-0007": {"SRC-003:L000225-L000371": ["SRC-003:L000225-L000335"]},
    "REQ-SCHED-0009": {"SRC-014:L000378-L000748": ["SRC-014:L000417-L000525"]},
    "REQ-SCHED-0010": {
        "SRC-014:L000378-L000748": [
            "SRC-014:L000417-L000602",
            "SRC-014:L000710-L000748",
        ]
    },
    "REQ-SCHED-0011": {"SRC-014:L000378-L000748": ["SRC-014:L000526-L000709"]},
    "REQ-SCHED-0013": {"SRC-014:L000378-L000748": ["SRC-014:L000710-L000748"]},
    "REQ-SCHED-0014": {"SRC-014:L000378-L000748": ["SRC-014:L000488-L000525"]},
    "REQ-SCHED-0016": {"SRC-014:L001548-L001747": ["SRC-014:L001548-L001580"]},
    "REQ-SCHED-0017": {"SRC-014:L000378-L000748": []},
    "REQ-SEC-0016": {"SRC-015:L000359-L000488": ["SRC-015:L000407-L000488"]},
    "REQ-UPSTREAM-0011": {"SRC-016:L001691-L001832": ["SRC-016:L001691-L001747"]},
    "REQ-UPSTREAM-0014": {"SRC-011:L001212-L001345": ["SRC-006:L000057-L000129"]},
    "REQ-UX-0014": {"SRC-006:L001806-L001929": ["SRC-006:L001806-L001884"]},
    "REQ-UX-0024": {"SRC-015:L000151-L000488": ["SRC-015:L000228-L000488"]},
    "REQ-UX-0026": {
        "SRC-002:L000516-L000680": [
            "SRC-002:L000577-L000680",
            "SRC-016:L001232-L001261",
        ]
    },
}


def _repair_source_references(requirement: dict[str, Any]) -> None:
    repairs = SOURCE_REFERENCE_REPAIRS.get(str(requirement["requirement_id"]), {})
    if not repairs:
        return
    repaired: list[str] = []
    for source in requirement["source_references"]:
        repaired.extend(repairs.get(str(source), [str(source)]))
    requirement["source_references"] = list(dict.fromkeys(repaired))


def _overlaps(left: str, right: str) -> bool:
    a = _SOURCE.fullmatch(left)
    b = _SOURCE.fullmatch(right)
    if a is None or b is None or a.group(1) != b.group(1):
        return False
    return int(a.group(2)) <= int(b.group(3)) and int(a.group(3)) >= int(b.group(2))


def _core_requirement() -> dict[str, object]:
    return {
        "acceptance_summary": (
            "Verified only when a complete local-real project journey and each ordered live, "
            "Windows, recovery, 24-hour, 72-hour, release, and post-release qualification stage "
            "observably execute the continuous loop and the deterministic Completion Gate passes."
        ),
        "authority_classification": "SOURCE_DERIVED",
        "decision_ids": [],
        "disposition": "ACCEPTED",
        "disposition_reason": (
            "Accepted because the original source explicitly defines the complete perpetual "
            "autonomous engineering loop and scoped human-escalation continuation behavior."
        ),
        "domain": "PDEF",
        "evidence_ids": [],
        "evolution_ids": ["SOURCE-EVOLUTION-0008"],
        "implementation_paths": [],
        "implementation_state": "PLANNED_ONLY",
        "jira_ids": [
            "PP-EPIC-000036",
            *[f"PP-STORY-{value:06d}" for value in range(138, 144)],
            *[f"PP-TASK-{value:06d}" for value in range(380, 386)],
        ],
        "normative_strength": "SHALL",
        "open_decision_ids": [],
        "plan_ids": ["PLAN-CTRL-003"],
        "plan_section_ids": [f"PLAN-CTRL-003:SEC-{value:02d}" for value in range(1, 8)],
        "priority": "P0",
        "rationale": (
            "This is the non-negotiable product outcome. Component existence, mocks, deterministic "
            "simulation, lifecycle state, or local preview cannot satisfy it."
        ),
        "requirement_id": CORE_REQUIREMENT_ID,
        "requirement_type": "functional",
        "risk": "CRITICAL",
        "schema_version": "2.0.0",
        "source_kind": "CANONICAL_SOURCE",
        "source_references": ["SRC-014:L000001-L000087", "SRC-015:L000001-L000113"],
        "source_sequence": 14,
        "statement": CORE_STATEMENT,
        "superseded_by_requirement_ids": [],
        "supersedes_requirement_ids": [],
        "tags": [
            "autonomy-runtime",
            "continuous-operation",
            "golden-journey",
            "pdef",
            "product-outcome",
            "unattended-qualification",
        ],
        "test_ids": [],
        "title": "Continuous autonomous engineering organization",
        "verification_class": "INDEPENDENT_MULTI_EVIDENCE",
        "verification_expectation": (
            "Verify observable end-to-end behavior at every ordered qualification environment; "
            "lower stages and mocks cannot substitute for live, duration, release, or post-release proof."
        ),
    }


def repair(root: Path) -> tuple[int, int]:
    contract = read_json(root / "config/product_outcome.json")
    section_contracts = contract["user_intent_contracts"]
    requirements_path = root / "plans/_traceability/requirements.jsonl"
    requirements = read_jsonl(requirements_path)
    by_id: dict[str, dict[str, Any]] = {str(item["requirement_id"]): item for item in requirements}
    intake = by_id["REQ-PDEF-0006"]
    old_reference = "SRC-014:L000005-L000209"
    intake["source_references"] = [
        "SRC-014:L000088-L000209" if item == old_reference else item
        for item in intake["source_references"]
    ]
    core = _core_requirement()
    if CORE_REQUIREMENT_ID in by_id:
        requirements = [
            core if item["requirement_id"] == CORE_REQUIREMENT_ID else item for item in requirements
        ]
    else:
        requirements.append(core)
    by_id[CORE_REQUIREMENT_ID] = core

    director = by_id["REQ-CTRL-0004"]
    director.update(
        {
            "acceptance_summary": (
                "Verified only when a persistent Autonomy Director observably drives strategic "
                "planning and next-work continuation above the deterministic Control Kernel; "
                "Director Chat alone is insufficient."
            ),
            "implementation_state": "PARTIALLY_IMPLEMENTED",
            "jira_ids": ["PP-EPIC-000007", "PP-STORY-000065", "PP-EPIC-000036", "PP-TASK-000381"],
            "risk": "CRITICAL",
            "source_references": [
                "SRC-003:L000005-L000084",
                "SRC-014:L000005-L000087",
            ],
            "statement": (
                "The Autonomy Director shall continuously interpret the verified project model, "
                "propose goals and plans, resolve ambiguity, coordinate strategic decisions, and "
                "direct next-work continuation above the deterministic Control Kernel without "
                "bypassing its policy or state-transition authority."
            ),
            "title": "Persistent Autonomy Director",
            "verification_expectation": (
                "Verify persistent, restart-safe strategic direction and autonomous next-work "
                "continuation in the integrated runtime; an operator chat response is not proof."
            ),
        }
    )
    for requirement_id in ("REQ-SEC-0002", "REQ-SEC-0017"):
        requirement = by_id[requirement_id]
        requirement["jira_ids"] = [
            item for item in requirement["jira_ids"] if item != "PP-TASK-000168"
        ]
    for requirement_id in ("REQ-SEC-0004", "REQ-SEC-0009"):
        requirement = by_id[requirement_id]
        requirement["jira_ids"] = sorted(
            set(requirement["jira_ids"]) | {"PP-TASK-000168"}
        )

    for requirement in requirements:
        _repair_source_references(requirement)

    sections_path = root / "plans/_traceability/source_sections.jsonl"
    sections = read_jsonl(sections_path)
    section_by_id = {str(item["section_id"]): item for item in sections}
    for section_id, requirement_ids in section_contracts.items():
        section = section_by_id[section_id]
        section_reference = str(section["source_reference"])
        for requirement_id in requirement_ids:
            requirement = by_id[requirement_id]
            references = list(requirement["source_references"])
            if not any(_overlaps(reference, section_reference) for reference in references):
                references.append(section_reference)
                requirement["source_references"] = references
        section["disposition"] = "REQUIREMENT_LINKED"
        section["disposition_reason"] = (
            "The initiating operator outcome is explicitly enforced by accepted requirements; "
            "the links are validated against overlapping exact source ranges."
        )
        section["requirement_ids"] = sorted(
            set(section.get("requirement_ids", [])) | set(requirement_ids)
        )

    # Recompute every source-section reverse link from exact range overlap so the broad-range repair
    # cannot leave a stale semantic claim behind.
    for section in sections:
        reference = str(section["source_reference"])
        linked = sorted(
            requirement_id
            for requirement_id, requirement in by_id.items()
            if any(_overlaps(source, reference) for source in requirement["source_references"])
        )
        section["requirement_ids"] = linked
        if linked and section["disposition"] == "USER_INTENT_CONTEXT":
            section["disposition"] = "REQUIREMENT_LINKED"
            section["disposition_reason"] = (
                "The initiating operator outcome is explicitly enforced by accepted requirements; "
                "the links are validated against overlapping exact source ranges."
            )
    write_jsonl(requirements_path, sorted(requirements, key=lambda item: item["requirement_id"]))
    write_jsonl(sections_path, sections)
    return len(requirements), len(section_contracts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    requirement_count, intent_count = repair(args.root.resolve())
    print(f"requirements={requirement_count} user_intent_contracts={intent_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
