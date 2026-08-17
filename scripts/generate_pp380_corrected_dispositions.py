from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

PRESERVE_RUNTIME_ACTION = "PRESERVE_OBSERVED_RUNTIME_EVIDENCE"
PRESERVE_UNKNOWN_OWNER_ACTION = "PRESERVE_OWNER_ATTESTATION_PENDING"
PROHIBITED_NOT_APPLICABLE = "NOT_APPLICABLE_PROHIBITED_SENSITIVE"
GENERATOR_VERSION = "pp380-generator-v1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(payload: str) -> str:
    return _sha256_bytes(payload.encode("utf-8"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _path_matches(map_row: dict[str, Any], row: dict[str, Any]) -> bool:
    return (
        map_row.get("workspace") == row.get("workspace")
        and map_row.get("status_code") == row.get("status_code")
        and map_row.get("path") == row.get("path")
    )


def _tree_fingerprint(repo_root: Path, relative_dir: str) -> str:
    directory = repo_root / relative_dir
    if not directory.exists() or not directory.is_dir():
        return "TREE_SHA256:ABSENT"
    fingerprints: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(repo_root).as_posix()
        content_hash = _sha256_bytes(path.read_bytes())
        fingerprints.append(f"{relative_path}\0{content_hash}")
    serialized = "\n".join(fingerprints)
    return f"TREE_SHA256:{_sha256_text(serialized)}"


def _normalize_row(row: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    normalized = dict(row)
    path = str(normalized.get("path", ""))
    original_category = str(normalized.get("original_category", ""))

    if original_category == "LOCAL_RUNTIME_EVIDENCE":
        normalized["proposed_final_action"] = PRESERVE_RUNTIME_ACTION
        normalized["cited_branch_or_ref"] = "N/A"
        normalized["cited_commit"] = "N/A"
        normalized["cited_path"] = "N/A"
        normalized["cited_blob_sha256"] = "N/A"
        normalized["content_equal"] = False
        normalized["semantic_reason"] = (
            f"Preserve observed runtime evidence artifact for {path}; do not regenerate or overwrite."
        )
        normalized["integration_condition"] = (
            "Archive-only preservation until explicit post-integration reconciliation authorizes replacement"
        )
    elif original_category == "UNKNOWN_OWNER":
        normalized["proposed_final_action"] = PRESERVE_UNKNOWN_OWNER_ACTION
        normalized["cited_branch_or_ref"] = "N/A"
        normalized["cited_commit"] = "N/A"
        normalized["cited_path"] = "N/A"
        normalized["cited_blob_sha256"] = "N/A"
        normalized["content_equal"] = False
        normalized["semantic_reason"] = f"Preserve {path} pending explicit ownership attestation."
        normalized["integration_condition"] = (
            "Retain unchanged until owner attestation and authoritative reconciliation are completed"
        )
    elif original_category == "PROHIBITED_SENSITIVE_STOP":
        normalized["original_source_sha256"] = PROHIBITED_NOT_APPLICABLE
        normalized["proposed_final_action"] = PRESERVE_UNKNOWN_OWNER_ACTION
        normalized["cited_branch_or_ref"] = "N/A"
        normalized["cited_commit"] = "N/A"
        normalized["cited_path"] = "N/A"
        normalized["cited_blob_sha256"] = "N/A"
        normalized["content_equal"] = False
        normalized["semantic_reason"] = (
            "Not applicable to record content hash for prohibited-sensitive planning artifact; preserve without mutation."
        )
        normalized["integration_condition"] = (
            "No mutation permitted without explicit security authority and owner-confirmed reconciliation"
        )

    if path.endswith("/") and normalized.get("original_source_sha256") == "UNKNOWN":
        normalized["original_source_sha256"] = _tree_fingerprint(repo_root, path.rstrip("/"))

    return normalized


def _render_markdown(
    document: dict[str, Any], source_ledger_path: Path, source_map_path: Path
) -> str:
    summary = document["summary"]
    generation_proof = document["generation_proof"]
    lines = [
        "# PP-380 Cycle 6 Corrected Dispositions",
        "",
        f"- Source ledger: `{source_ledger_path.as_posix()}`",
        f"- Source map: `{source_map_path.as_posix()}`",
        f"- Row count: `{summary['row_count']}`",
        f"- Prior equivalence claims evaluated: `{summary['equivalence_claim_rows']}`",
        f"- True exact-content equivalence rows: `{summary['equivalence_true']}`",
        f"- Divergent equivalence rows reclassified: `{summary['equivalence_false']}`",
        "",
        "## Action counts",
    ]
    for action, count in sorted(summary["action_counts"].items()):
        lines.append(f"- `{action}`: `{count}`")
    lines.extend(
        [
            "",
            "## Generation proof",
            f"- Generator version: `{generation_proof['generator_version']}`",
            f"- Source map SHA-256: `{generation_proof['source_map_sha256']}`",
            f"- Source ledger SHA-256: `{generation_proof['source_ledger_sha256']}`",
            f"- Rows SHA-256: `{generation_proof['rows_sha256']}`",
            f"- Verification receipt SHA-256: `{generation_proof['verification_receipt_sha256']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-ledger", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--input-corrected", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    source_ledger_path = args.source_ledger.resolve()
    source_map_path = args.source_map.resolve()
    input_corrected_path = args.input_corrected.resolve()

    source_ledger = source_ledger_path.read_text(encoding="utf-8")
    source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
    corrected_input = json.loads(input_corrected_path.read_text(encoding="utf-8"))
    source_map_rows = source_map.get("rows")
    rows = corrected_input.get("rows")
    if not isinstance(source_map_rows, list) or not isinstance(rows, list):
        raise ValueError("source map and corrected input must both contain rows lists")
    if len(source_map_rows) != len(rows):
        raise ValueError("row count mismatch between source map and corrected input")

    for index, (map_row, row) in enumerate(zip(source_map_rows, rows, strict=True), start=1):
        if not _path_matches(map_row, row):
            raise ValueError(
                f"row alignment mismatch at index {index}: {map_row.get('path')} vs {row.get('path')}"
            )

    normalized_rows = [_normalize_row(row, repo_root) for row in rows]
    action_counts: dict[str, int] = dict(
        Counter(str(row["proposed_final_action"]) for row in normalized_rows)
    )
    equivalence_claim_rows = sum(
        1 for row in normalized_rows if row["cited_commit"] not in {"N/A", "UNKNOWN"}
    )
    equivalence_true = sum(
        1
        for row in normalized_rows
        if row["proposed_final_action"] == "SUPERSEDED_BY_EXACT_PR_HEAD_AND_EQUIVALENCE"
    )
    rows_sha256 = _sha256_text(_canonical_json(normalized_rows))
    source_map_sha256 = _sha256_text(source_map_path.read_text(encoding="utf-8"))
    source_ledger_sha256 = _sha256_text(source_ledger)
    receipt_payload = {
        "generator_version": GENERATOR_VERSION,
        "source_map_sha256": source_map_sha256,
        "source_ledger_sha256": source_ledger_sha256,
        "rows_sha256": rows_sha256,
    }
    receipt = _sha256_text(_canonical_json(receipt_payload))

    document = {
        "summary": {
            "schema_version": "1.1.0",
            "source_cycle5_disposition": source_ledger_path.as_posix(),
            "source_reconciliation_map": source_map_path.as_posix(),
            "row_count": len(normalized_rows),
            "equivalence_claim_rows": equivalence_claim_rows,
            "equivalence_true": equivalence_true,
            "equivalence_false": equivalence_claim_rows - equivalence_true,
            "action_counts": action_counts,
        },
        "generation_proof": {
            "generator_version": GENERATOR_VERSION,
            "source_map_sha256": source_map_sha256,
            "source_ledger_sha256": source_ledger_sha256,
            "rows_sha256": rows_sha256,
            "verification_receipt_sha256": receipt,
        },
        "rows": normalized_rows,
    }

    args.output_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text(
        _render_markdown(document, source_ledger_path, source_map_path),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
