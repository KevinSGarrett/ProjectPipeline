from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl, sha256_file, write_json

INSPECTED_STATES = {"DEEPLY_REVIEWED", "FOCUSED_REVIEW_COMPLETE", "SOURCE_LEVEL_REVIEW_COMPLETE"}
ACTIVATION_QUALIFIED_STATES = {"DEEPLY_REVIEWED", "FOCUSED_REVIEW_COMPLETE"}
ADOPTION_DISPOSITIONS = {"ADOPT_DEPENDENCY", "ADAPT_COMPONENT"}
MINED_DISPOSITIONS = {"MINE_ARCHITECTURE", "MINE_IMPLEMENTATION_PATTERN", "MINE_TEST_PATTERN"}
IMPLEMENTED_USAGE_STATES = {
    "ACTIVE_RUNTIME",
    "OPTIONAL_ADAPTER_IMPLEMENTED",
    "EXTERNAL_CLI_ADAPTER_IMPLEMENTED",
    "INCORPORATED_ASSET",
    "ARCHITECTURE_PATTERN_ADOPTED",
    "IMPLEMENTATION_PATTERN_ADOPTED",
    "TEST_PATTERN_ADOPTED",
}
ALLOWED_USAGE_STATES = IMPLEMENTED_USAGE_STATES | {
    "SELECTED_NOT_ACTIVATED",
    "FUTURE_SUBSYSTEM_BOUNDARY",
}


def load_upstream_registry(root: Path) -> dict[str, Any]:
    return read_json(root / "provenance" / "upstream_registry.json")


def load_p0_convergence(root: Path) -> dict[str, Any]:
    path = root / "provenance" / "p0_convergence.json"
    return read_json(path) if path.exists() else {"status": "NOT_AVAILABLE", "records": []}


def load_upstream_usage(root: Path) -> list[dict[str, Any]]:
    path = root / "provenance" / "upstream_usage.jsonl"
    return read_jsonl(path) if path.exists() else []


def upstream_index(root: Path) -> dict[str, dict[str, Any]]:
    return {item["upstream_id"]: item for item in load_upstream_registry(root).get("entries", [])}


def find_upstreams(
    root: Path,
    *,
    upstream_id: str | None = None,
    repository: str | None = None,
    disposition: str | None = None,
    inspection_state: str | None = None,
    subsystem: str | None = None,
    text: str | None = None,
) -> list[dict[str, Any]]:
    query = text.casefold() if text else None
    result: list[dict[str, Any]] = []
    for item in load_upstream_registry(root).get("entries", []):
        full_name = f"{item['owner']}/{item['repository']}"
        if upstream_id and item.get("upstream_id") != upstream_id:
            continue
        if repository and full_name.casefold() != repository.casefold():
            continue
        if disposition and item.get("disposition") != disposition:
            continue
        if inspection_state and item.get("inspection_state") != inspection_state:
            continue
        if subsystem and item.get("candidate_subsystem") != subsystem:
            continue
        if query:
            searchable = " ".join(
                str(item.get(field, ""))
                for field in (
                    "upstream_id",
                    "canonical_url",
                    "purpose",
                    "candidate_subsystem",
                    "disposition",
                    "disposition_rationale",
                    "architectural_lessons",
                )
            ).casefold()
            if query not in searchable:
                continue
        result.append(item)
    return sorted(result, key=lambda item: item["upstream_id"])


def summarize_upstreams(root: Path) -> dict[str, Any]:
    registry = load_upstream_registry(root)
    entries = registry.get("entries", [])
    reviewed = [item for item in entries if item.get("inspection_state") in INSPECTED_STATES]
    adopted = [item for item in entries if item.get("disposition") in ADOPTION_DISPOSITIONS]
    usage = load_upstream_usage(root)
    usage_by_state = Counter(item.get("usage_state", "UNKNOWN") for item in usage)
    return {
        "schema_version": "2.0.0",
        "entry_count": len(entries),
        "deep_review_count": len(reviewed),
        "adoption_count": len(adopted),
        "by_disposition": dict(sorted(Counter(item["disposition"] for item in entries).items())),
        "by_inspection_state": dict(
            sorted(Counter(item["inspection_state"] for item in entries).items())
        ),
        "licenses_reviewed": dict(sorted(Counter(item["license"] for item in reviewed).items())),
        "dependency_activation_eligible_count": sum(
            bool(item.get("dependency_activation_eligible")) for item in entries
        ),
        "incorporation_allowed_count": sum(
            bool(item.get("incorporation_allowed")) for item in entries
        ),
        "source_incorporation_approved_count": sum(
            item.get("source_incorporation_state") == "APPROVED_BOUNDED" for item in entries
        ),
        "catalog_review_complete": bool(registry.get("catalog_review_complete")),
        "terminal_disposition_count": sum(
            item.get("disposition") != "EVALUATE_LATER" for item in entries
        ),
        "evaluate_later_count": sum(
            item.get("disposition") == "EVALUATE_LATER" for item in entries
        ),
        "usage_record_count": len(usage),
        "implemented_usage_count": sum(
            item.get("usage_state") in IMPLEMENTED_USAGE_STATES for item in usage
        ),
        "active_dependency_count": usage_by_state.get("ACTIVE_RUNTIME", 0),
        "optional_adapter_count": usage_by_state.get("OPTIONAL_ADAPTER_IMPLEMENTED", 0),
        "external_cli_adapter_count": usage_by_state.get("EXTERNAL_CLI_ADAPTER_IMPLEMENTED", 0),
        "selected_not_activated_count": usage_by_state.get("SELECTED_NOT_ACTIVATED", 0)
        + usage_by_state.get("FUTURE_SUBSYSTEM_BOUNDARY", 0),
        "by_usage_state": dict(sorted(usage_by_state.items())),
    }


def render_upstream_summary(root: Path) -> str:
    summary = summarize_upstreams(root)
    registry = load_upstream_registry(root)
    usage_index = {item["upstream_id"]: item for item in load_upstream_usage(root)}
    rows = [
        item
        for item in registry.get("entries", [])
        if item.get("inspection_state") in INSPECTED_STATES
    ]
    lines = [
        "# Upstream Evaluation and Use Summary",
        "",
        f"- Cataloged repositories: `{summary['entry_count']}`",
        f"- Focused, deep, or source-level reviews complete: `{summary['deep_review_count']}`",
        f"- Terminal catalog dispositions: `{summary['terminal_disposition_count']}`",
        f"- Remaining EVALUATE_LATER entries: `{summary['evaluate_later_count']}`",
        f"- Direct dependency/component selections: `{summary['adoption_count']}`",
        f"- Implemented upstream usages: `{summary['implemented_usage_count']}`",
        f"- Active runtime dependencies: `{summary['active_dependency_count']}`",
        f"- Optional adapters implemented: `{summary['optional_adapter_count']}`",
        f"- External CLI adapters implemented: `{summary['external_cli_adapter_count']}`",
        f"- Bounded source adaptations approved: `{summary['source_incorporation_approved_count']}`",
        f"- Selected but not activated: `{summary['selected_not_activated_count']}`",
        "",
        "## Reviewed repositories",
        "",
    ]
    for item in rows:
        full_name = f"{item['owner']}/{item['repository']}"
        usage = usage_index.get(item["upstream_id"], {})
        lines.extend(
            [
                f"### {item['upstream_id']} — {full_name}",
                "",
                f"- Disposition: `{item['disposition']}`",
                f"- Usage state: `{usage.get('usage_state', 'NOT_SELECTED')}`",
                f"- License: `{item['license']}`",
                f"- Inspected revision: `{item['inspected_revision']}`",
                f"- Dependency activation eligible: `{str(bool(item.get('dependency_activation_eligible'))).lower()}`",
                f"- Bounded source adaptation approved: `{str(item.get('source_incorporation_state') == 'APPROVED_BOUNDED').lower()}`",
                f"- Project Pipeline role: {item['purpose']}",
                f"- Integration paths: `{', '.join(usage.get('integration_paths', [])) or 'none'}`",
                f"- Review: [`{item['review_artifact']}`](reviews/{Path(item['review_artifact']).name})",
                "",
            ]
        )
    lines.extend(
        [
            "## Retrieval",
            "",
            "Use `PYTHONPATH=src python -m project_pipeline upstream --root . --summary` for a machine-readable summary.",
            "Use `--id`, `--repository`, `--disposition`, `--inspection-state`, `--subsystem`, or `--text` for focused retrieval.",
        ]
    )
    return "\n".join(lines)


def write_upstream_views(root: Path) -> dict[str, Any]:
    summary = summarize_upstreams(root)
    write_json(root / "provenance" / "upstream_summary.json", summary)
    path = root / "provenance" / "UPSTREAM_REVIEW_SUMMARY.md"
    path.write_text(render_upstream_summary(root).rstrip() + "\n", encoding="utf-8", newline="\n")
    return {
        "deep_review_count": summary["deep_review_count"],
        "adoption_count": summary["adoption_count"],
        "paths": ["provenance/upstream_summary.json", "provenance/UPSTREAM_REVIEW_SUMMARY.md"],
    }


def validate_upstream_reviews(root: Path) -> list[str]:
    errors: list[str] = []
    registry = load_upstream_registry(root)
    entries = registry.get("entries", [])
    reviewed = [item for item in entries if item.get("inspection_state") in INSPECTED_STATES]
    adopted = [item for item in entries if item.get("disposition") in ADOPTION_DISPOSITIONS]
    if registry.get("deep_review_count") != len(reviewed):
        errors.append("Upstream deep_review_count is stale")
    if registry.get("adoption_count") != len(adopted):
        errors.append("Upstream adoption_count is stale")
    if registry.get("entry_count") != len(entries):
        errors.append("Upstream entry_count is stale")

    policy_path = root / "provenance" / "license_policy.json"
    program_path = root / "provenance" / "review_program.json"
    usage_path = root / "provenance" / "upstream_usage.jsonl"
    if not policy_path.exists():
        errors.append("License policy is missing")
        return errors
    if not program_path.exists():
        errors.append("Upstream review program is missing")
        return errors
    if not usage_path.exists():
        errors.append("Upstream usage ledger is missing")
        return errors
    policy = read_json(policy_path)
    program = read_json(program_path)
    usage = load_upstream_usage(root)
    auto_approved = set(policy.get("automatic_approval_spdx", []))
    review_required = set(policy.get("review_required_spdx", []))
    prohibited = set(policy.get("prohibited_spdx", []))
    ids = {item["upstream_id"] for item in entries}
    usage_ids = [item.get("upstream_id") for item in usage]
    if len(usage_ids) != len(set(usage_ids)):
        errors.append("Upstream usage ledger contains duplicate upstream IDs")
    usage_index = {item["upstream_id"]: item for item in usage if item.get("upstream_id")}

    for item in entries:
        upstream_id = item["upstream_id"]
        if not item.get("disposition_rationale"):
            errors.append(f"Upstream {upstream_id} lacks disposition rationale")
        copied = item.get("copied_source_paths", [])
        allowed = bool(item.get("incorporation_allowed"))
        if copied or allowed:
            if (
                not copied
                or not allowed
                or item.get("source_incorporation_state") != "APPROVED_BOUNDED"
            ):
                errors.append(
                    f"Upstream {upstream_id} has incomplete bounded source-adaptation approval"
                )
            review_path = (
                root / "provenance" / "source_incorporation_reviews" / f"{upstream_id}.json"
            )
            if not review_path.exists():
                errors.append(f"Upstream {upstream_id} lacks a source-incorporation review")
            else:
                review = read_json(review_path)
                if review.get("approval_state") != "APPROVED_BOUNDED":
                    errors.append(f"Upstream {upstream_id} source review is not approved")
                if review.get("license") not in auto_approved:
                    errors.append(
                        f"Upstream {upstream_id} source adaptation license is not auto-approved"
                    )
                if set(review.get("project_paths", [])) != set(copied):
                    errors.append(
                        f"Upstream {upstream_id} source review paths differ from registry"
                    )
                notice = root / review.get("notice_path", "")
                if not notice.exists():
                    errors.append(f"Upstream {upstream_id} source adaptation notice is missing")
                for relative in copied:
                    path = root / relative
                    if not path.exists():
                        errors.append(
                            f"Upstream {upstream_id} adapted source path is missing: {relative}"
                        )
                    expected = review.get("project_sha256", {}).get(relative)
                    if path.exists() and expected != sha256_file(path):
                        errors.append(
                            f"Upstream {upstream_id} adapted source hash is stale: {relative}"
                        )
        if item.get("disposition") in ADOPTION_DISPOSITIONS:
            record = usage_index.get(upstream_id)
            if record is None:
                errors.append(f"Adopted upstream {upstream_id} lacks a usage ledger record")
            else:
                if record.get("usage_state") not in ALLOWED_USAGE_STATES:
                    errors.append(
                        f"Upstream {upstream_id} has invalid usage state {record.get('usage_state')}"
                    )
                for relative in record.get("integration_paths", []):
                    if not (root / relative).exists():
                        errors.append(
                            f"Upstream {upstream_id} integration path is missing: {relative}"
                        )

    for item in reviewed:
        upstream_id = item["upstream_id"]
        required = {
            "purpose",
            "candidate_subsystem",
            "license",
            "inspected_revision",
            "upstream_revision",
            "useful_concepts",
            "useful_files",
            "integration_possibilities",
            "architectural_lessons",
            "security_concerns",
            "portability_concerns",
            "maintenance_concerns",
            "maturity",
            "compatibility",
            "dependency_implications",
            "review_artifact",
            "reviewed_at_utc",
            "evidence_sources",
        }
        missing = sorted(
            field for field in required if field not in item or item[field] in (None, "", [])
        )
        if missing:
            errors.append(f"Deep review {upstream_id} lacks fields: {missing}")
        review_artifact = root / item.get("review_artifact", "")
        if not review_artifact.exists():
            errors.append(
                f"Deep review artifact is missing for {upstream_id}: {item.get('review_artifact')}"
            )
        revision = item.get("inspected_revision", "")
        if not revision or revision in {"NOT_INSPECTED", "UNKNOWN"}:
            errors.append(f"Reviewed upstream {upstream_id} lacks an inspected revision")
        license_id = item.get("license")
        if license_id in prohibited and item.get("dependency_activation_eligible"):
            errors.append(f"Prohibited-license upstream {upstream_id} is activation eligible")
        if item.get("disposition") in ADOPTION_DISPOSITIONS:
            if license_id not in auto_approved and license_id not in review_required:
                errors.append(
                    f"Adopted upstream {upstream_id} has unclassified license {license_id}"
                )
            if item.get("inspection_state") in ACTIVATION_QUALIFIED_STATES and not item.get(
                "dependency_activation_eligible"
            ):
                errors.append(
                    f"Activation-qualified upstream {upstream_id} is not eligible for dependency activation"
                )
            if item.get("inspection_state") not in ACTIVATION_QUALIFIED_STATES and item.get(
                "dependency_activation_eligible"
            ):
                errors.append(
                    f"Upstream {upstream_id} is activation eligible before focused/deep qualification"
                )
        elif item.get("dependency_activation_eligible"):
            errors.append(f"Non-adopted upstream {upstream_id} is marked activation eligible")
        if item.get("disposition") in MINED_DISPOSITIONS and item.get(
            "dependency_activation_eligible"
        ):
            errors.append(
                f"Pattern-mining upstream {upstream_id} is incorrectly activation eligible"
            )

    gate_path = root / "provenance" / "upstream_adoption_gate.json"
    dispositions_path = root / "provenance" / "catalog_dispositions.jsonl"
    queue_path = root / "provenance" / "adoption_queue.json"
    if not gate_path.exists():
        errors.append("Upstream Adoption Gate is missing")
    else:
        gate = read_json(gate_path)
        if gate.get("catalog_review_complete"):
            unresolved = [
                item["upstream_id"]
                for item in entries
                if item.get("disposition") == "EVALUATE_LATER"
            ]
            if unresolved:
                errors.append(
                    f"Catalog review is marked complete but EVALUATE_LATER remains: {unresolved}"
                )
            if registry.get("terminal_disposition_count") != len(entries):
                errors.append("Terminal upstream disposition count is stale")
        known_ids = {item["upstream_id"] for item in entries}
        for subsystem, record in gate.get("subsystems", {}).items():
            candidates = record.get("candidate_upstream_ids", [])
            if not candidates:
                errors.append(f"Upstream Adoption Gate subsystem {subsystem} has no candidate set")
            unknown = sorted(set(candidates) - known_ids)
            if unknown:
                errors.append(
                    f"Upstream Adoption Gate subsystem {subsystem} references unknown IDs: {unknown}"
                )
            if record.get("review_state") not in {
                "CATALOG_CONSIDERED",
                "FOCUSED_REVIEW_COMPLETE",
                "INTEGRATED",
            }:
                errors.append(
                    f"Upstream Adoption Gate subsystem {subsystem} lacks a valid review state"
                )
    if not dispositions_path.exists():
        errors.append("Terminal upstream catalog disposition ledger is missing")
    else:
        disposition_rows = read_jsonl(dispositions_path)
        if len(disposition_rows) != len(entries):
            errors.append(
                "Terminal upstream catalog disposition ledger does not cover every catalog entry"
            )
        if {row.get("upstream_id") for row in disposition_rows} != {
            item["upstream_id"] for item in entries
        }:
            errors.append("Terminal upstream catalog disposition ledger IDs differ from registry")
    if not queue_path.exists():
        errors.append("Upstream adoption queue is missing")

    convergence_path = root / "provenance" / "p0_convergence.json"
    if convergence_path.exists():
        convergence = read_json(convergence_path)
        queue = read_json(queue_path) if queue_path.exists() else {}
        p0_ids: set[str] = set()
        for priority in queue.get("priorities", []):
            if priority.get("priority") == "P0":
                p0_ids.update(priority.get("upstream_ids", []))
        records = {row.get("upstream_id"): row for row in convergence.get("records", [])}
        if convergence.get("status") != "PASS":
            errors.append("P0 upstream implementation convergence is not PASS")
        if set(records) != p0_ids:
            errors.append("P0 convergence ledger does not exactly cover the P0 adoption queue")
        for upstream_id in sorted(p0_ids):
            row = records.get(upstream_id, {})
            usage_record = usage_index.get(upstream_id, {})
            if row.get("convergence_outcome") == "IMPLEMENTED_ADAPTER":
                if usage_record.get("usage_state") not in IMPLEMENTED_USAGE_STATES:
                    errors.append(
                        f"P0 upstream {upstream_id} claims adapter convergence without implemented usage"
                    )
                for relative in row.get("integration_paths", []):
                    if not (root / relative).exists():
                        errors.append(
                            f"P0 upstream {upstream_id} integration path is missing: {relative}"
                        )
                for relative in row.get("test_paths", []):
                    if not (root / relative).exists():
                        errors.append(f"P0 upstream {upstream_id} test path is missing: {relative}")
            elif row.get("convergence_outcome") not in {
                "EXPLICITLY_DEFERRED",
                "BLOCKED_EXTERNAL",
                "REJECTED_AFTER_REVIEW",
            }:
                errors.append(f"P0 upstream {upstream_id} has invalid convergence outcome")
        if (
            bool(convergence.get("pass_12_upstream_prerequisite_satisfied")) != (not errors)
            and convergence.get("pass_12_upstream_prerequisite_satisfied")
            and any(
                message.startswith("P0 upstream") or message.startswith("P0 convergence")
                for message in errors
            )
        ):
            errors.append(
                "P0 convergence incorrectly claims the Pass 12 upstream prerequisite is satisfied"
            )

    for item in entries:
        upstream_id = item["upstream_id"]
        disposition = item.get("disposition")
        if (
            registry.get("catalog_review_complete")
            and item.get("catalog_review_state") != "TERMINAL_DISPOSITION_RECORDED"
        ):
            errors.append(f"Upstream {upstream_id} lacks terminal catalog review state")
        if disposition in {"REJECT", "NOT_RELEVANT"} and not item.get("disposition_rationale"):
            errors.append(f"Closed upstream {upstream_id} lacks rejection/not-relevant rationale")
        if (
            disposition in MINED_DISPOSITIONS
            and not item.get("architectural_lessons")
            and not item.get("integration_possibilities")
        ):
            errors.append(
                f"Mined upstream {upstream_id} lacks recorded lessons or integration possibilities"
            )
        if disposition in ADOPTION_DISPOSITIONS:
            record = usage_index.get(upstream_id)
            if record:
                implemented = record.get("usage_state") in IMPLEMENTED_USAGE_STATES
                paths = record.get("integration_paths", [])
                if implemented and not paths:
                    errors.append(
                        f"Upstream {upstream_id} claims implemented usage without integration paths"
                    )
                if not implemented and paths:
                    errors.append(
                        f"Upstream {upstream_id} has integration paths but is not in an implemented usage state"
                    )
                if (
                    record.get("usage_state")
                    in {"SELECTED_NOT_ACTIVATED", "FUTURE_SUBSYSTEM_BOUNDARY"}
                    and record.get("reason", "").lower().find("concrete") >= 0
                    and paths
                ):
                    errors.append(
                        f"Upstream {upstream_id} selection state conflicts with integration evidence"
                    )
            if item.get("license") in {
                "LICENSE_NOT_RESOLVED",
                "LICENSE_FILE_PRESENT_UNRESOLVED",
                "UNKNOWN_NOT_INSPECTED",
            } and item.get("dependency_activation_eligible"):
                errors.append(
                    f"Upstream {upstream_id} has unresolved license but is activation eligible"
                )

    completed_ids = set(program.get("completed_review_ids", []))
    if completed_ids != {item["upstream_id"] for item in reviewed}:
        errors.append("Review program completed IDs differ from reviewed upstream records")
    for cohort in program.get("review_cohorts", []):
        for upstream_id in cohort.get("upstream_ids", []):
            if upstream_id not in ids:
                errors.append(f"Review program links unknown upstream {upstream_id}")

    summary_path = root / "provenance" / "upstream_summary.json"
    markdown_path = root / "provenance" / "UPSTREAM_REVIEW_SUMMARY.md"
    if not summary_path.exists() or read_json(summary_path) != summarize_upstreams(root):
        errors.append("Generated upstream summary JSON is missing or stale")
    expected_markdown = render_upstream_summary(root).rstrip() + "\n"
    if not markdown_path.exists() or markdown_path.read_text(encoding="utf-8") != expected_markdown:
        errors.append("Generated upstream summary Markdown is missing or stale")
    return errors
