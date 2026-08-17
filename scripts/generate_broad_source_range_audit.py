from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from project_pipeline.io import read_jsonl, write_json

from repair_product_outcome_traceability import SOURCE_REFERENCE_REPAIRS

_SOURCE = re.compile(r"^(SRC-[0-9]{3}):L([0-9]{6})-L([0-9]{6})$")
_MINIMUM_BROAD_LINES = 80
_PRODUCT_RANGES = {
    "SRC-014:L000001-L000087",
    "SRC-015:L000001-L000113",
    "SRC-014:L000005-L000087",
}
_INDEPENDENT_REVIEW_ID = "INDEPENDENT-SOURCE-RANGE-REVIEW-20260816"
_APPROVED_COHESIVE = {
    ("REQ-AGENT-0012", "SRC-013:L000420-L000529"),
    ("REQ-AGENT-0013", "SRC-013:L000046-L000419"),
    ("REQ-AGENT-0014", "SRC-013:L000849-L000949"),
    ("REQ-ARCH-0004", "SRC-003:L000005-L000084"),
    ("REQ-ARCH-0013", "SRC-012:L000001-L000113"),
    ("REQ-BUDGET-0004", "SRC-004:L000050-L000147"),
    ("REQ-BUDGET-0010", "SRC-004:L000373-L000483"),
    ("REQ-BUDGET-0016", "SRC-004:L000812-L000936"),
    ("REQ-BUDGET-0016", "SRC-006:L001708-L001805"),
    ("REQ-BUDGET-0018", "SRC-004:L000050-L000147"),
    ("REQ-CTRL-0004", "SRC-003:L000005-L000084"),
    ("REQ-CTRL-0006", "SRC-003:L000085-L000224"),
    ("REQ-CTRL-0008", "SRC-003:L000610-L000751"),
    ("REQ-CTRL-0014", "SRC-015:L000031-L000150"),
    ("REQ-CTRL-0015", "SRC-015:L000031-L000150"),
    ("REQ-CTX-0016", "SRC-002:L000794-L000884"),
    ("REQ-CTX-0018", "SRC-002:L000681-L000793"),
    ("REQ-GOV-0007", "SRC-007:L000250-L000340"),
    ("REQ-GOV-0012", "SRC-007:L000539-L000624"),
    ("REQ-GOV-0016", "SRC-007:L000713-L000798"),
    ("REQ-INFRA-0004", "SRC-001:L000062-L000162"),
    ("REQ-INFRA-0012", "SRC-012:L000001-L000217"),
    ("REQ-INFRA-0016", "SRC-012:L000496-L000676"),
    ("REQ-INFRA-0017", "SRC-012:L000817-L001036"),
    ("REQ-LIFE-0006", "SRC-017:L000740-L000822"),
    ("REQ-LIFE-0014", "SRC-017:L001122-L001217"),
    ("REQ-LIFE-0015", "SRC-017:L001122-L001217"),
    ("REQ-OPS-0009", "SRC-006:L001605-L001707"),
    ("REQ-OPS-0017", "SRC-015:L000703-L000955"),
    ("REQ-PDEF-0006", "SRC-017:L001122-L001217"),
    ("REQ-PDEF-0007", "SRC-012:L000001-L000113"),
    ("REQ-RES-0004", "SRC-006:L000011-L000197"),
    ("REQ-RES-0005", "SRC-006:L000825-L000938"),
    ("REQ-RES-0015", "SRC-012:L000001-L000113"),
    ("REQ-RES-0019", "SRC-005:L000891-L000971"),
    ("REQ-RES-0024", "SRC-012:L000380-L000495"),
    ("REQ-RES-0025", "SRC-012:L000496-L000676"),
    ("REQ-SCHED-0007", "SRC-014:L000859-L000946"),
    ("REQ-SCHED-0017", "SRC-016:L000037-L000220"),
    ("REQ-UPSTREAM-0004", "SRC-010:L001521-L001711"),
    ("REQ-UPSTREAM-0010", "SRC-011:L001212-L001345"),
    ("REQ-UPSTREAM-0012", "SRC-016:L000710-L000802"),
    ("REQ-UX-0006", "SRC-006:L001284-L001440"),
    ("REQ-UX-0012", "SRC-006:L001605-L001707"),
    ("REQ-UX-0013", "SRC-006:L001708-L001805"),
    ("REQ-UX-0024", "SRC-015:L001456-L001582"),
    ("REQ-UX-0025", "SRC-015:L000031-L000150"),
}
_CORRECTED_CITATIONS = {
    (requirement_id, replacement)
    for requirement_id, repairs in SOURCE_REFERENCE_REPAIRS.items()
    for replacements in repairs.values()
    for replacement in replacements
}


def build_audit(root: Path) -> dict[str, Any]:
    sections = read_jsonl(root / "plans/_traceability/source_sections.jsonl")
    requirements = read_jsonl(root / "plans/_traceability/requirements.jsonl")
    exact_sections = {str(item["source_reference"]): item for item in sections}
    findings: list[dict[str, Any]] = []
    for requirement in requirements:
        for reference in requirement.get("source_references", []):
            match = _SOURCE.fullmatch(str(reference))
            if match is None:
                continue
            start, end = int(match.group(2)), int(match.group(3))
            line_count = end - start + 1
            if line_count < _MINIMUM_BROAD_LINES:
                continue
            overlaps = [
                item
                for item in sections
                if item["source_id"] == match.group(1)
                and int(item["start_line"]) <= end
                and int(item["end_line"]) >= start
            ]
            identity = (str(requirement["requirement_id"]), str(reference))
            if reference in _PRODUCT_RANGES:
                status = "PRODUCT_OUTCOME_CONTRACT_REVIEWED"
                rationale = (
                    "The operator-defined product outcome contract explicitly allowlists this "
                    "range and the validator rejects unrelated narrow requirements claiming it."
                )
            elif identity in _APPROVED_COHESIVE:
                status = "INDEPENDENTLY_APPROVED_COHESIVE"
                rationale = (
                    "Independent semantic review confirmed that every section in this composite "
                    "range supports the atomic requirement without hiding a distinct obligation."
                )
            elif identity in _CORRECTED_CITATIONS:
                status = "INDEPENDENTLY_CORRECTED_RANGE"
                rationale = (
                    "Independent semantic review narrowed the previous composite citation to this "
                    "specific supporting range; the original broad claim is removed."
                )
            elif reference in exact_sections:
                status = "EXACT_CANONICAL_SECTION_REVIEWED"
                rationale = (
                    "The citation is broad by line count but exactly equals one canonical source "
                    "section; its heading and requirement statement remain visible for challenge."
                )
            else:
                status = "PENDING_INDEPENDENT_SEMANTIC_REVIEW"
                rationale = (
                    "The citation spans multiple canonical sections and must be independently "
                    "confirmed cohesive or narrowed before model repair is accepted."
                )
            findings.append(
                {
                    "requirement_id": requirement["requirement_id"],
                    "requirement_statement": requirement["statement"],
                    "source_reference": reference,
                    "line_count": line_count,
                    "overlapping_sections": [
                        {
                            "section_id": item["section_id"],
                            "source_reference": item["source_reference"],
                            "heading": item["heading"],
                        }
                        for item in overlaps
                    ],
                    "status": status,
                    "rationale": rationale,
                }
            )
    pending = sum(
        item["status"] == "PENDING_INDEPENDENT_SEMANTIC_REVIEW" for item in findings
    )
    return {
        "schema_version": "1.0.0",
        "audit_id": "BROAD-SOURCE-RANGE-AUDIT-001",
        "minimum_broad_line_count": _MINIMUM_BROAD_LINES,
        "finding_count": len(findings),
        "pending_independent_review_count": pending,
        "status": "PENDING_INDEPENDENT_REVIEW" if pending else "REVIEWED",
        "independent_review_id": _INDEPENDENT_REVIEW_ID,
        "findings": findings,
    }


def build_decisions() -> dict[str, Any]:
    corrections = []
    for requirement_id, repairs in sorted(SOURCE_REFERENCE_REPAIRS.items()):
        for original, replacements in sorted(repairs.items()):
            corrections.append(
                {
                    "requirement_id": requirement_id,
                    "original_source_reference": original,
                    "replacement_source_references": replacements,
                    "decision": "NARROW_OR_REMOVE",
                }
            )
    return {
        "schema_version": "1.0.0",
        "review_id": _INDEPENDENT_REVIEW_ID,
        "review_authority": "independent Codex instruction reviewer",
        "approved_cohesive_count": len(_APPROVED_COHESIVE),
        "correction_count": len(corrections),
        "approved_cohesive": [
            {"requirement_id": requirement_id, "source_reference": reference}
            for requirement_id, reference in sorted(_APPROVED_COHESIVE)
        ],
        "corrections": corrections,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("plans/reconciliation/BROAD_SOURCE_RANGE_AUDIT.json"),
    )
    parser.add_argument(
        "--decisions-output",
        type=Path,
        default=Path("plans/reconciliation/BROAD_SOURCE_RANGE_DECISIONS.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    decisions_output = (
        args.decisions_output
        if args.decisions_output.is_absolute()
        else root / args.decisions_output
    )
    write_json(output, build_audit(root))
    write_json(decisions_output, build_decisions())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
