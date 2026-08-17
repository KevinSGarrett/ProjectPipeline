from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

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


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_show_blob(repo_root: Path, commit: str, path: str) -> bytes | None:
    command = ["git", "-C", str(repo_root), "show", f"{commit}:{path}"]
    result = subprocess.run(command, check=False, capture_output=True)
    if result.returncode != 0:
        return None
    return result.stdout


def validate_pp380_corrected_dispositions(repo_root: Path, document_path: Path) -> list[str]:
    document = json.loads(document_path.read_text(encoding="utf-8"))
    rows = document.get("rows")
    if not isinstance(rows, list):
        return ["rows must be a list"]

    errors: list[str] = []
    if len(rows) != 325:
        errors.append(f"expected 325 rows, found {len(rows)}")

    row_ids: set[int] = set()
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
        cited_commit = str(row.get("cited_commit"))
        cited_path = str(row.get("cited_path"))
        original_hash = str(row.get("original_source_sha256"))
        cited_blob_sha256 = str(row.get("cited_blob_sha256"))
        content_equal = bool(row.get("content_equal"))

        blob = None
        if cited_commit not in {"N/A", "UNKNOWN"} and cited_path not in {"N/A", "UNKNOWN"}:
            blob = _git_show_blob(repo_root, cited_commit, cited_path)

        if action == "SUPERSEDED_BY_EXACT_PR_HEAD_AND_EQUIVALENCE":
            if blob is None:
                errors.append(f"row {row_id} equivalence target blob is missing")
                continue
            target_hash = _sha256_bytes(blob)
            if target_hash != cited_blob_sha256:
                errors.append(f"row {row_id} cited blob hash does not match git blob content")
            if target_hash != original_hash:
                errors.append(f"row {row_id} claims equivalence without matching hashes")
            if not content_equal:
                errors.append(f"row {row_id} equivalence row must set content_equal=true")

        if action == "COMMIT_UNIQUE_PP380_DELTA" and blob is None:
            errors.append(f"row {row_id} COMMIT row path absent from cited commit")

        if content_equal and blob is not None and _sha256_bytes(blob) != original_hash:
            errors.append(f"row {row_id} sets content_equal=true but hashes differ")

    return errors
