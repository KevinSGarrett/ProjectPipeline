from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from project_pipeline.assurance import build_repository_gate_facts, evaluate_completion_gate
from project_pipeline.release_hardening import build_release_candidate

_EXTERNAL_MARKERS = (
    "aws",
    "cloud",
    "remote jira",
    "github",
    "deployment",
    "windows",
    "desktop",
    "docker",
    "terraform",
    "external system",
    "external mutation",
    "provider",
    "gpu",
    "network access",
    "live-verified",
    "live verified",
)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _audit_dimensions(
    root: Path,
    requirements: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    usages: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted = [r for r in requirements if r.get("disposition") == "ACCEPTED"]
    plan_files = sorted(root.glob("plans/**/PLAN-*.md"))
    jira_graph = _json(root / "jira/relationships/graph.json")
    test_catalog = _json(root / "tests/TEST_CATALOG.json")
    adr_catalog = _json(root / "adr/ADR_CATALOG.json")
    golden = _json(root / "evidence/verification/golden_journeys.json")
    e2e_matrix = _json(root / "config/pass23_e2e_journey_matrix.json")
    runbook_files = sorted(
        path for path in (root / "runbooks").glob("*.md") if path.name != "README.md"
    )
    deployment_paths = [
        "infrastructure/aws/terraform/main.tf",
        "infrastructure/docker/Dockerfile",
        "infrastructure/docker/compose.yaml",
        "infrastructure/windows/ProjectPipelineService.xml",
        "config/runtime/profiles/production.json",
        "docs/operations/INSTALLATION_AND_OPERATIONS.md",
    ]
    security_paths = [
        "config/security_policy.json",
        "policies/security/action_policy.rego",
        "SECURITY.md",
    ]
    dependency_paths = [
        "config/dependency_policy.json",
        "provenance/upstream_usage.jsonl",
        "requirements/environment.lock.json",
    ]
    source_link_missing = [r["requirement_id"] for r in accepted if not r.get("source_references")]
    implementation_mapping_missing = [
        r["requirement_id"]
        for r in accepted
        if r.get("implementation_state") in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"}
        and not r.get("implementation_paths")
    ]
    test_mapping_missing = [
        r["requirement_id"]
        for r in accepted
        if r.get("implementation_state") in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"}
        and not r.get("test_ids")
    ]
    evidence_mapping_missing = [
        r["requirement_id"]
        for r in accepted
        if r.get("implementation_state") in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"}
        and not r.get("evidence_ids")
    ]
    dimension_missing = {
        "requirement_dispositions": []
        if len(accepted) == len(requirements)
        else ["non-accepted requirements require explicit disposition audit"],
        "plan_areas": [] if plan_files else ["no PLAN-*.md files found"],
        "work_relationships": []
        if jira_graph.get("edge_count", 0) > 0
        else ["Jira relationship graph has no edges"],
        "implementation_mappings": implementation_mapping_missing,
        "tests": test_mapping_missing
        if test_catalog.get("test_count", 0) > 0
        else ["test catalog missing or empty"],
        "evidence": evidence_mapping_missing if evidence else ["evidence ledger missing or empty"],
        "decisions": [] if adr_catalog.get("decisions") else ["ADR catalog missing or empty"],
        "dependencies": [path for path in dependency_paths if not (root / path).exists()],
        "security_controls": [path for path in security_paths if not (root / path).exists()],
        "journeys": []
        if golden and e2e_matrix
        else [
            path
            for path in (
                "evidence/verification/golden_journeys.json",
                "config/pass23_e2e_journey_matrix.json",
            )
            if not (root / path).exists()
        ],
        "deployment_artifacts": [path for path in deployment_paths if not (root / path).exists()],
        "runbooks": [] if runbook_files else ["no runbooks found"],
        "blockers": [],
        "source_links": source_link_missing,
        "upstream_usage": [] if usages else ["upstream usage registry missing or empty"],
    }
    return {
        "dimension_count": len(dimension_missing),
        "dimensions": {
            key: {"covered": not value, "missing": value}
            for key, value in dimension_missing.items()
        },
        "counts": {
            "accepted_requirements": len(accepted),
            "plan_files": len(plan_files),
            "jira_issues": len(issues),
            "jira_relationship_edges": int(jira_graph.get("edge_count", 0)),
            "tests": int(test_catalog.get("test_count", 0)),
            "evidence_records": len(evidence),
            "adrs": len(adr_catalog.get("decisions", [])),
            "upstream_usages": len(usages),
            "runbooks": len(runbook_files),
            "golden_journey_records": len(
                golden if isinstance(golden, list) else golden.get("journeys", [])
            )
            if golden
            else 0,
        },
        "all_dimensions_covered": all(not value for value in dimension_missing.values()),
    }


def _requirement_classification(item: dict[str, Any]) -> tuple[str, str]:
    state = item.get("implementation_state")
    if state == "IMPLEMENTED":
        return "COMPLETE_LOCAL_OR_EVIDENCED", "requirement registry records implementation complete"
    text = " ".join(
        [str(item.get("title", "")), str(item.get("statement", "")), " ".join(item.get("tags", []))]
    ).lower()
    if any(marker in text for marker in _EXTERNAL_MARKERS):
        return (
            "EXTERNAL_OR_TARGET_QUALIFICATION_REQUIRED",
            "requirement depends on an external/target runtime or live integration boundary that cannot be inferred from source-only evidence",
        )
    if state == "PARTIALLY_IMPLEMENTED":
        return (
            "LOCALLY_PARTIAL_REQUIRES_BREADTH_OR_INDEPENDENT_EVIDENCE",
            "some implementation exists but accepted scope or independent evidence remains incomplete",
        )
    return (
        "LOCAL_SCOPE_REMAINS_INCOMPLETE",
        "accepted requirement remains planned-only and is not being hidden by final-audit status",
    )


def build_convergence_audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    requirements = _jsonl(root / "plans/_traceability/requirements.jsonl")
    issues = _jsonl(root / "jira/indexes/issues.jsonl")
    evidence = _jsonl(root / "evidence/EVIDENCE_LEDGER.jsonl")
    usages = _jsonl(root / "provenance/upstream_usage.jsonl")
    accepted = [r for r in requirements if r.get("disposition") == "ACCEPTED"]
    classified = []
    for item in accepted:
        category, reason = _requirement_classification(item)
        classified.append(
            {
                "requirement_id": item["requirement_id"],
                "priority": item.get("priority"),
                "domain": item.get("domain"),
                "implementation_state": item.get("implementation_state"),
                "classification": category,
                "reason": reason,
                "implementation_paths": item.get("implementation_paths", []),
                "test_ids": item.get("test_ids", []),
                "evidence_ids": item.get("evidence_ids", []),
                "jira_ids": item.get("jira_ids", []),
                "plan_ids": item.get("plan_ids", []),
                "source_references": item.get("source_references", []),
            }
        )
    non_epic_orphans = [
        i.get("local_id")
        for i in issues
        if i.get("issue_type") != "EPIC"
        and not (i.get("requirement_ids") or i.get("plan_references") or i.get("source_references"))
    ]
    unresolved_decisions = []
    decision_path = root / "plans/01_requirements/OPEN_DECISIONS.jsonl"
    if decision_path.exists():
        unresolved_decisions = [
            d.get("decision_id")
            for d in _jsonl(decision_path)
            if d.get("status") not in {"RESOLVED", "REJECTED", "SUPERSEDED"}
        ]
    upstream_nonterminal = [
        u.get("upstream_id") for u in usages if u.get("usage_state") in {None, "UNKNOWN", "PENDING"}
    ]
    gate = evaluate_completion_gate(build_repository_gate_facts(root, "PROJECT-PIPELINE"))
    candidate = build_release_candidate(root)
    dimensions = _audit_dimensions(root, requirements, issues, evidence, usages)
    counts = Counter(row["classification"] for row in classified)
    audit_complete = (
        not non_epic_orphans
        and not upstream_nonterminal
        and len(classified) == len(accepted)
        and dimensions["all_dimensions_covered"]
    )
    return {
        "schema_version": "1.0.0",
        "audit_id": "PASS-25-FINAL-CONVERGENCE-AUDIT",
        "audit_complete": audit_complete,
        "project_complete": gate.state.value == "COMPLETE",
        "completion_gate_state": gate.state.value,
        "completion_gate_failed_questions": [
            q.question_number for q in gate.questions if not q.passed
        ],
        "accepted_requirement_count": len(accepted),
        "classification_counts": dict(sorted(counts.items())),
        "requirements": classified,
        "jira_issue_count": len(issues),
        "orphan_non_epic_jira_ids": non_epic_orphans,
        "evidence_record_count": len(evidence),
        "unresolved_decision_ids": unresolved_decisions,
        "upstream_usage_count": len(usages),
        "upstream_nonterminal_usage_ids": upstream_nonterminal,
        "audit_dimensions": dimensions,
        "repository_validation_reference": "evidence/final_convergence_pass25_repository_validation.txt",
        "release_candidate": {
            "readiness": candidate.readiness,
            "production_ready": False,
            "blockers": list(candidate.blockers),
        },
        "truth_boundary": "audit completion means the convergence audit itself covered the repository; it does not override incomplete requirements, missing live target evidence, or the independent Completion Gate",
    }
