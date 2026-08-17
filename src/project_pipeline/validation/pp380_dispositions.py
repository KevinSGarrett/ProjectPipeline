from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

_REQUIRED_FIELDS = (
    "row_id",
    "workspace",
    "status_code",
    "path",
    "original_source_sha256",
    "original_category",
    "owner_task",
    "authority_classification",
    "proposed_final_action",
    "cited_commit",
    "cited_path",
    "cited_blob_sha256",
    "content_equal",
    "semantic_reason",
    "integration_condition",
)

_HEX64 = set("0123456789abcdef")
_PRESERVE_RUNTIME_ACTION = "PRESERVE_OBSERVED_RUNTIME_EVIDENCE"
_PRESERVE_UNKNOWN_OWNER_ACTION = "PRESERVE_OWNER_ATTESTATION_PENDING"
_PROHIBITED_NOT_APPLICABLE = "NOT_APPLICABLE_PROHIBITED_SENSITIVE"
_RECEIPT_KEYS = (
    "generator_version",
    "source_map_sha256",
    "source_ledger_sha256",
    "rows_sha256",
    "verification_receipt_sha256",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(payload: str) -> str:
    return _sha256_bytes(payload.encode("utf-8"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_hex_sha256(value: str) -> bool:
    lowered = value.lower()
    return len(lowered) == 64 and all(character in _HEX64 for character in lowered)


def _rows_digest(rows: list[dict[str, Any]]) -> str:
    return _sha256_text(_canonical_json(rows))


def _expected_receipt(document: dict[str, Any], rows_sha256: str) -> str:
    generation_proof = document.get("generation_proof", {})
    receipt_payload = {
        "generator_version": generation_proof.get("generator_version"),
        "source_map_sha256": generation_proof.get("source_map_sha256"),
        "source_ledger_sha256": generation_proof.get("source_ledger_sha256"),
        "rows_sha256": rows_sha256,
    }
    return _sha256_text(_canonical_json(receipt_payload))


def validate_pp380_corrected_dispositions(repo_root: Path, document_path: Path) -> list[str]:
    document = json.loads(document_path.read_text(encoding="utf-8"))
    rows = document.get("rows")
    if not isinstance(rows, list):
        return ["rows must be a list"]

    errors: list[str] = []
    summary = document.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        declared_count = summary.get("row_count")
        if declared_count != len(rows):
            errors.append(
                f"summary row_count mismatch: expected {len(rows)}, found {declared_count}"
            )

    row_ids: set[int] = set()
    action_counter: Counter[str] = Counter()
    for row in rows:
        row_id = row.get("row_id")
        if not isinstance(row_id, int):
            errors.append("row_id must be an integer")
            continue
        if row_id in row_ids:
            errors.append(f"duplicate row_id detected: {row_id}")
        row_ids.add(row_id)

        for field in _REQUIRED_FIELDS:
            if field not in row:
                errors.append(f"row {row_id} missing required field: {field}")
                continue
            value = row.get(field)
            if value is None:
                errors.append(f"row {row_id} has blank required field: {field}")
            if isinstance(value, str) and not value.strip():
                errors.append(f"row {row_id} has blank required field: {field}")

        action = row.get("proposed_final_action")
        if isinstance(action, str):
            action_counter[action] += 1
        cited_commit = str(row.get("cited_commit"))
        original_hash = str(row.get("original_source_sha256"))
        cited_blob_sha256 = str(row.get("cited_blob_sha256"))
        content_equal = bool(row.get("content_equal"))
        original_category = str(row.get("original_category"))
        path = str(row.get("path"))

        if action == "SUPERSEDED_BY_EXACT_PR_HEAD_AND_EQUIVALENCE":
            if original_hash != cited_blob_sha256:
                errors.append(f"row {row_id} claims equivalence without matching hashes")
            if not content_equal:
                errors.append(f"row {row_id} equivalence row must set content_equal=true")
            if not _is_hex_sha256(original_hash):
                errors.append(f"row {row_id} equivalence row must use SHA-256 digests")

        if action == "COMMIT_UNIQUE_PP380_DELTA" and cited_commit in {"N/A", "UNKNOWN"}:
            errors.append(f"row {row_id} COMMIT row must cite a concrete commit")

        if original_category == "LOCAL_RUNTIME_EVIDENCE" and action != _PRESERVE_RUNTIME_ACTION:
            errors.append(f"row {row_id} runtime evidence must preserve observed artifact")

        if original_category == "UNKNOWN_OWNER" and action != _PRESERVE_UNKNOWN_OWNER_ACTION:
            errors.append(
                f"row {row_id} unknown owner row must remain preserved pending attestation"
            )

        if original_category == "PROHIBITED_SENSITIVE_STOP":
            if original_hash != _PROHIBITED_NOT_APPLICABLE:
                errors.append(
                    f"row {row_id} prohibited-sensitive row must use explicit not-applicable hash marker"
                )
            if "not applicable" not in str(row.get("semantic_reason", "")).lower():
                errors.append(
                    f"row {row_id} prohibited-sensitive row requires machine-valid not-applicable reason"
                )

        if path.endswith("/") and original_hash == "UNKNOWN":
            errors.append(
                f"row {row_id} directory summary row must carry deterministic tree fingerprint"
            )
        if path.endswith("/") and not (
            _is_hex_sha256(original_hash)
            or original_hash.startswith("TREE_SHA256:")
            or original_hash == _PROHIBITED_NOT_APPLICABLE
        ):
            errors.append(f"row {row_id} directory summary row has invalid fingerprint format")

    if len(row_ids) != len(rows):
        errors.append("row_id set is not unique")
    elif row_ids and row_ids != set(range(1, len(rows) + 1)):
        errors.append("row_id values must be a contiguous 1..N range")

    summary = document.get("summary", {})
    action_counts = summary.get("action_counts")
    if not isinstance(action_counts, dict):
        errors.append("summary.action_counts must be an object")
    else:
        for action, count in sorted(action_counter.items()):
            if action_counts.get(action) != count:
                errors.append(
                    f"summary.action_counts mismatch for {action}: expected {count}, found {action_counts.get(action)}"
                )

    generation_proof = document.get("generation_proof")
    if not isinstance(generation_proof, dict):
        errors.append("generation_proof must be an object")
    else:
        for key in _RECEIPT_KEYS:
            value = generation_proof.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"generation_proof missing required field: {key}")
        rows_sha256 = _rows_digest(rows)
        if generation_proof.get("rows_sha256") != rows_sha256:
            errors.append("generation_proof rows_sha256 does not match rows payload")
        expected_receipt = _expected_receipt(document, rows_sha256)
        if generation_proof.get("verification_receipt_sha256") != expected_receipt:
            errors.append("generation_proof verification receipt is invalid")

    return errors
