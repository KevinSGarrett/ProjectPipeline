from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

PRESERVE_RUNTIME_ACTION = "PRESERVE_OBSERVED_RUNTIME_EVIDENCE"
PRESERVE_UNKNOWN_OWNER_ACTION = "PRESERVE_OWNER_ATTESTATION_PENDING"
PROHIBITED_NOT_APPLICABLE = "NOT_APPLICABLE_PROHIBITED_SENSITIVE"
EQUIVALENCE_ACTION = "SUPERSEDED_BY_EXACT_PR_HEAD_AND_EQUIVALENCE"
COMMIT_UNIQUE_ACTION = "COMMIT_UNIQUE_PP380_DELTA"
GENERATOR_VERSION = "pp380-generator-v2"
RECEIPT_KIND = "content_addressed_source_bound_not_signed"
DEFAULT_SOURCE_LEDGER = "evidence/pp380_cycle5_execution_dispositions.json"
DEFAULT_SOURCE_MAP = "evidence/pp380_source_reconciliation_map.json"
DEFAULT_OUTPUT_JSON = "evidence/pp380_cycle6_corrected_dispositions.json"
DEFAULT_OUTPUT_MD = "evidence/pp380_cycle6_corrected_dispositions.md"
PR44_DEFAULT = "2a82fc53f6422fd13aaf308f7024bf6850f49b01"
PR46_DEFAULT = "626a365fad876e3e834830f208e9d05092899fd9"
EQUIVALENCE_CATEGORIES = frozenset({"SUPERSEDED_BY_PR44", "SUPERSEDED_BY_PR46"})
EXPECTED_EQUIVALENCE_CLAIMS = 64
EXPECTED_EQUIVALENCE_TRUE = 8
EXPECTED_EQUIVALENCE_FALSE = 56

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
_RECEIPT_KEYS = (
    "generator_version",
    "receipt_kind",
    "source_map_sha256",
    "source_ledger_sha256",
    "rows_sha256",
    "self_consistent_hash_sha256",
    "content_addressed_receipt_sha256",
    "git_ref_receipts",
)


class GitObjectResolver(Protocol):
    def resolve_commit(self, ref: str) -> str: ...

    def blob_sha256(self, commit: str, relative_path: str) -> str | None: ...


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_source_bytes(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _sha256_text(payload: str) -> str:
    return _sha256_bytes(payload.encode("utf-8"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_hex_sha256(value: str) -> bool:
    lowered = value.lower()
    return len(lowered) == 64 and all(character in _HEX64 for character in lowered)


def _posix_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix().replace("\\", "/")


def tree_fingerprint(repo_root: Path, relative_dir: str) -> str:
    directory = repo_root / relative_dir
    if not directory.exists() or not directory.is_dir():
        return "TREE_SHA256:ABSENT"
    fingerprints: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(repo_root).as_posix()
        fingerprints.append(f"{relative_path}\0{_sha256_bytes(path.read_bytes())}")
    return f"TREE_SHA256:{_sha256_text(chr(10).join(fingerprints))}"


def self_consistent_hash(
    *,
    generator_version: str,
    source_map_sha256: str,
    source_ledger_sha256: str,
    rows_sha256: str,
) -> str:
    return _sha256_text(
        _canonical_json(
            {
                "generator_version": generator_version,
                "source_map_sha256": source_map_sha256,
                "source_ledger_sha256": source_ledger_sha256,
                "rows_sha256": rows_sha256,
            }
        )
    )


def content_addressed_receipt(
    *,
    generator_version: str,
    source_map_bytes: bytes,
    source_ledger_bytes: bytes,
    git_ref_receipts: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    payload = b"".join(
        (
            generator_version.encode("utf-8"),
            b"\n",
            source_map_bytes,
            b"\n",
            source_ledger_bytes,
            b"\n",
            _canonical_json(git_ref_receipts).encode("utf-8"),
            b"\n",
            _canonical_json(rows).encode("utf-8"),
        )
    )
    return _sha256_bytes(payload)


@dataclass(frozen=True)
class SubprocessGitResolver:
    repo_root: Path

    def resolve_commit(self, ref: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.repo_root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ValueError(f"git ref is not resolvable: {ref}")
        sha = completed.stdout.strip()
        probe = subprocess.run(
            ["git", "-C", str(self.repo_root), "cat-file", "-e", f"{sha}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            raise ValueError(f"git object is missing: {sha}")
        return sha

    def blob_sha256(self, commit: str, relative_path: str) -> str | None:
        if relative_path.endswith("/"):
            return None
        completed = subprocess.run(
            ["git", "-C", str(self.repo_root), "show", f"{commit}:{relative_path}"],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            return None
        return _sha256_bytes(completed.stdout)


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("workspace", "")),
        str(row.get("status_code", "")),
        str(row.get("path", "")),
    )


def _original_hash(map_row: dict[str, Any], repo_root: Path) -> str | None:
    path = str(map_row.get("path", ""))
    raw = map_row.get("sha256")
    if path.endswith("/") and raw in {None, "", "UNKNOWN"}:
        return tree_fingerprint(repo_root, path.rstrip("/"))
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw


def _derive_row(
    *,
    ledger_row: dict[str, Any],
    map_row: dict[str, Any],
    repo_root: Path,
    git: GitObjectResolver,
    pr44_sha: str,
    pr46_sha: str,
    pp380_sha: str,
    pr44_ref: str,
    pr46_ref: str,
    pp380_ref: str,
) -> dict[str, Any]:
    category = str(ledger_row.get("original_category", ""))
    map_category = str(map_row.get("current_category", ""))
    if category != map_category:
        raise ValueError(
            f"category mismatch for {_row_key(ledger_row)}: ledger={category} map={map_category}"
        )
    path = str(ledger_row.get("path", ""))
    if category == "PROHIBITED_SENSITIVE_STOP":
        original_hash = PROHIBITED_NOT_APPLICABLE
        action = PRESERVE_UNKNOWN_OWNER_ACTION
        cited_ref = "N/A"
        cited_commit = "N/A"
        cited_path = "N/A"
        cited_blob = "N/A"
        content_equal = False
        reason = (
            "Not applicable to record content hash for prohibited-sensitive planning artifact; "
            "preserve without mutation."
        )
        condition = "No mutation permitted without explicit security authority and owner-confirmed reconciliation"
    elif category == "LOCAL_RUNTIME_EVIDENCE":
        computed = _original_hash(map_row, repo_root)
        if computed is None:
            raise ValueError(f"source map row missing sha256 for {path}")
        original_hash = computed
        action = PRESERVE_RUNTIME_ACTION
        cited_ref = "N/A"
        cited_commit = "N/A"
        cited_path = "N/A"
        cited_blob = "N/A"
        content_equal = False
        reason = f"Preserve observed runtime evidence artifact for {path}; do not regenerate or overwrite."
        condition = "Archive-only preservation until explicit post-integration reconciliation authorizes replacement"
    elif category == "UNKNOWN_OWNER":
        computed = _original_hash(map_row, repo_root)
        if computed is None:
            raise ValueError(f"source map row missing sha256 for {path}")
        original_hash = computed
        action = PRESERVE_UNKNOWN_OWNER_ACTION
        cited_ref = "N/A"
        cited_commit = "N/A"
        cited_path = "N/A"
        cited_blob = "N/A"
        content_equal = False
        reason = f"Preserve {path} pending explicit ownership attestation."
        condition = "Retain unchanged until owner attestation and authoritative reconciliation are completed"
    elif category == "SUPERSEDED_BY_PR44":
        computed = _original_hash(map_row, repo_root)
        if computed is None:
            raise ValueError(f"source map row missing sha256 for {path}")
        original_hash = computed
        cited_ref = pr44_ref
        cited_commit = pr44_sha
        cited_path = path
        cited_blob = git.blob_sha256(pr44_sha, path) or "ABSENT"
        content_equal = bool(_is_hex_sha256(original_hash) and original_hash == cited_blob)
        action = EQUIVALENCE_ACTION if content_equal else "THREE_WAY_RECONCILE_AFTER_PR44"
        reason = (
            "Exact preserved-source SHA-256 equals cited PR-head blob SHA-256"
            if content_equal
            else "Equivalence claim rejected: preserved-source SHA-256 does not match cited PR-head blob"
        )
        condition = (
            "Apply cited PR head before PP-380; no path-local reconcile needed"
            if content_equal
            else "After PR #44 is integrated, perform three-way reconcile on cited path"
        )
    elif category == "SUPERSEDED_BY_PR46":
        computed = _original_hash(map_row, repo_root)
        if computed is None:
            raise ValueError(f"source map row missing sha256 for {path}")
        original_hash = computed
        cited_ref = pr46_ref
        cited_commit = pr46_sha
        cited_path = path
        cited_blob = git.blob_sha256(pr46_sha, path) or "ABSENT"
        content_equal = bool(_is_hex_sha256(original_hash) and original_hash == cited_blob)
        action = EQUIVALENCE_ACTION if content_equal else "THREE_WAY_RECONCILE_AFTER_PR46"
        reason = (
            "Exact preserved-source SHA-256 equals cited PR-head blob SHA-256"
            if content_equal
            else "Equivalence claim rejected: preserved-source SHA-256 does not match cited PR-head blob"
        )
        condition = (
            "Apply cited PR head before PP-380; no path-local reconcile needed"
            if content_equal
            else "After PR #46 is integrated, perform three-way reconcile on cited path"
        )
    elif category == "UNIQUE_ACCEPTANCE_WORK":
        computed = _original_hash(map_row, repo_root)
        if computed is None:
            raise ValueError(f"source map row missing sha256 for {path}")
        original_hash = computed
        action = COMMIT_UNIQUE_ACTION
        cited_ref = pp380_ref
        cited_commit = pp380_sha
        cited_path = path
        cited_blob = git.blob_sha256(pp380_sha, path) or "ABSENT"
        content_equal = bool(_is_hex_sha256(original_hash) and original_hash == cited_blob)
        reason = (
            "Path is unique PP-380 implementation delta and is retained on PP-380 commit boundary"
        )
        condition = (
            "Integrate cited PP-380 commit after prerequisite PR merge order and validations"
        )
    else:
        raise ValueError(f"unsupported original_category: {category}")

    return {
        "row_id": ledger_row["row_id"],
        "workspace": ledger_row["workspace"],
        "status_code": ledger_row["status_code"],
        "path": path,
        "original_source_sha256": original_hash,
        "original_category": category,
        "owner_task": ledger_row["owner_task"],
        "authority_classification": ledger_row["authority_classification"],
        "proposed_final_action": action,
        "cited_branch_or_ref": cited_ref,
        "cited_commit": cited_commit,
        "cited_path": cited_path,
        "cited_blob_sha256": cited_blob,
        "content_equal": content_equal,
        "semantic_reason": reason,
        "integration_condition": condition,
    }


def generate_pp380_corrected_dispositions(
    *,
    repo_root: Path,
    source_ledger_path: Path,
    source_map_path: Path,
    pr44_ref: str = PR44_DEFAULT,
    pr46_ref: str = PR46_DEFAULT,
    pp380_ref: str | None = None,
    git: GitObjectResolver | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    source_ledger_path = source_ledger_path.resolve()
    source_map_path = source_map_path.resolve()
    source_ledger_bytes = _canonical_source_bytes(source_ledger_path.read_bytes())
    source_map_bytes = _canonical_source_bytes(source_map_path.read_bytes())
    ledger = json.loads(source_ledger_bytes.decode("utf-8"))
    source_map = json.loads(source_map_bytes.decode("utf-8"))
    ledger_rows = ledger.get("rows")
    map_rows = source_map.get("rows")
    if not isinstance(ledger_rows, list) or not isinstance(map_rows, list):
        raise ValueError("source ledger and source map must both contain rows lists")
    map_by_key = {_row_key(row): row for row in map_rows}
    if len(map_by_key) != len(map_rows):
        raise ValueError("source map contains duplicate workspace/status/path keys")
    resolver = git or SubprocessGitResolver(repo_root)
    pr44_sha = resolver.resolve_commit(pr44_ref)
    pr46_sha = resolver.resolve_commit(pr46_ref)
    default_pp380 = None
    commits = ledger.get("summary", {}).get("commits", {})
    if isinstance(commits, dict):
        default_pp380 = commits.get("pp380")
    resolved_pp380_ref = pp380_ref or (default_pp380 if isinstance(default_pp380, str) else None)
    if not resolved_pp380_ref:
        raise ValueError("pp380 unique ref is required")
    pp380_sha = resolver.resolve_commit(resolved_pp380_ref)

    derived_rows: list[dict[str, Any]] = []
    for ledger_row in ledger_rows:
        key = _row_key(ledger_row)
        map_row = map_by_key.get(key)
        if map_row is None:
            raise ValueError(f"source map missing row for {key}")
        derived_rows.append(
            _derive_row(
                ledger_row=ledger_row,
                map_row=map_row,
                repo_root=repo_root,
                git=resolver,
                pr44_sha=pr44_sha,
                pr46_sha=pr46_sha,
                pp380_sha=pp380_sha,
                pr44_ref=pr44_ref,
                pr46_ref=pr46_ref,
                pp380_ref=resolved_pp380_ref,
            )
        )

    action_counts = dict(Counter(str(row["proposed_final_action"]) for row in derived_rows))
    equivalence_claim_rows = sum(
        1 for row in derived_rows if row["original_category"] in EQUIVALENCE_CATEGORIES
    )
    equivalence_true = sum(
        1 for row in derived_rows if row["proposed_final_action"] == EQUIVALENCE_ACTION
    )
    rows_sha256 = _sha256_text(_canonical_json(derived_rows))
    source_map_sha256 = _sha256_bytes(source_map_bytes)
    source_ledger_sha256 = _sha256_bytes(source_ledger_bytes)
    git_ref_receipts = {
        "pr44": {"requested_ref": pr44_ref, "resolved_sha": pr44_sha},
        "pr46": {"requested_ref": pr46_ref, "resolved_sha": pr46_sha},
        "pp380_unique": {"requested_ref": resolved_pp380_ref, "resolved_sha": pp380_sha},
    }
    document = {
        "summary": {
            "schema_version": "1.2.0",
            "source_cycle5_disposition": _posix_relative(source_ledger_path, repo_root),
            "source_reconciliation_map": _posix_relative(source_map_path, repo_root),
            "row_count": len(derived_rows),
            "equivalence_claim_rows": equivalence_claim_rows,
            "equivalence_true": equivalence_true,
            "equivalence_false": equivalence_claim_rows - equivalence_true,
            "action_counts": action_counts,
        },
        "generation_proof": {
            "generator_version": GENERATOR_VERSION,
            "receipt_kind": RECEIPT_KIND,
            "source_map_sha256": source_map_sha256,
            "source_ledger_sha256": source_ledger_sha256,
            "rows_sha256": rows_sha256,
            "self_consistent_hash_sha256": self_consistent_hash(
                generator_version=GENERATOR_VERSION,
                source_map_sha256=source_map_sha256,
                source_ledger_sha256=source_ledger_sha256,
                rows_sha256=rows_sha256,
            ),
            "content_addressed_receipt_sha256": content_addressed_receipt(
                generator_version=GENERATOR_VERSION,
                source_map_bytes=source_map_bytes,
                source_ledger_bytes=source_ledger_bytes,
                git_ref_receipts=git_ref_receipts,
                rows=derived_rows,
            ),
            "git_ref_receipts": git_ref_receipts,
        },
        "rows": derived_rows,
    }
    return document


def render_pp380_markdown(document: dict[str, Any]) -> str:
    summary = document["summary"]
    proof = document["generation_proof"]
    lines = [
        "# PP-380 Cycle 6 Corrected Dispositions",
        "",
        f"- Source ledger: `{summary['source_cycle5_disposition']}`",
        f"- Source map: `{summary['source_reconciliation_map']}`",
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
            f"- Generator version: `{proof['generator_version']}`",
            f"- Receipt kind: `{proof['receipt_kind']}`",
            f"- Source map SHA-256: `{proof['source_map_sha256']}`",
            f"- Source ledger SHA-256: `{proof['source_ledger_sha256']}`",
            f"- Rows SHA-256: `{proof['rows_sha256']}`",
            f"- Self-consistent hash SHA-256: `{proof['self_consistent_hash_sha256']}`",
            f"- Content-addressed receipt SHA-256: `{proof['content_addressed_receipt_sha256']}`",
            "",
            "The content-addressed receipt binds generator version, exact source-map bytes, "
            "exact source-ledger bytes, resolved Git object IDs, and the derived rows. It is "
            "not a cryptographic signature. A self-consistent hash of values already stored in "
            "this document is not an acceptance proof.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_pp380_outputs(document: dict[str, Any], output_json: Path, output_md: Path) -> None:
    output_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    output_md.write_text(render_pp380_markdown(document), encoding="utf-8", newline="\n")


def validate_pp380_corrected_dispositions(
    repo_root: Path,
    document_path: Path,
    *,
    verify_sources: bool = True,
    git: GitObjectResolver | None = None,
) -> list[str]:
    repo_root = repo_root.resolve()
    document = json.loads(document_path.read_text(encoding="utf-8"))
    rows = document.get("rows")
    if not isinstance(rows, list):
        return ["rows must be a list"]

    errors: list[str] = []
    summary = document.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        if summary.get("row_count") != len(rows):
            errors.append(
                f"summary row_count mismatch: expected {len(rows)}, found {summary.get('row_count')}"
            )
        for field in (
            "source_cycle5_disposition",
            "source_reconciliation_map",
        ):
            value = summary.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"summary missing portable source identifier: {field}")
            elif Path(value).is_absolute() or ":" in value.split("/", 1)[0]:
                errors.append(f"summary.{field} must be a repository-relative portable path")

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
            if value is None or (isinstance(value, str) and not value.strip()):
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
        if action == EQUIVALENCE_ACTION:
            if original_hash != cited_blob_sha256:
                errors.append(f"row {row_id} claims equivalence without matching hashes")
            if not content_equal:
                errors.append(f"row {row_id} equivalence row must set content_equal=true")
            if not _is_hex_sha256(original_hash):
                errors.append(f"row {row_id} equivalence row must use SHA-256 digests")
        if action == COMMIT_UNIQUE_ACTION and cited_commit in {"N/A", "UNKNOWN"}:
            errors.append(f"row {row_id} COMMIT row must cite a concrete commit")
        if original_category == "LOCAL_RUNTIME_EVIDENCE" and action != PRESERVE_RUNTIME_ACTION:
            errors.append(f"row {row_id} runtime evidence must preserve observed artifact")
        if original_category == "UNKNOWN_OWNER" and action != PRESERVE_UNKNOWN_OWNER_ACTION:
            errors.append(
                f"row {row_id} unknown owner row must remain preserved pending attestation"
            )
        if original_category == "PROHIBITED_SENSITIVE_STOP":
            if original_hash != PROHIBITED_NOT_APPLICABLE:
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
            or original_hash == PROHIBITED_NOT_APPLICABLE
        ):
            errors.append(f"row {row_id} directory summary row has invalid fingerprint format")

    if len(row_ids) != len(rows):
        errors.append("row_id set is not unique")
    elif row_ids and row_ids != set(range(1, len(rows) + 1)):
        errors.append("row_id values must be a contiguous 1..N range")

    action_counts = summary.get("action_counts") if isinstance(summary, dict) else None
    if not isinstance(action_counts, dict):
        errors.append("summary.action_counts must be an object")
    else:
        for action, count in sorted(action_counter.items()):
            if action_counts.get(action) != count:
                errors.append(
                    f"summary.action_counts mismatch for {action}: expected {count}, found {action_counts.get(action)}"
                )

    equivalence_claim_rows = sum(
        1 for row in rows if str(row.get("original_category")) in EQUIVALENCE_CATEGORIES
    )
    equivalence_true = sum(
        1 for row in rows if row.get("proposed_final_action") == EQUIVALENCE_ACTION
    )
    if isinstance(summary, dict):
        if summary.get("equivalence_claim_rows") != equivalence_claim_rows:
            errors.append(
                "summary.equivalence_claim_rows must count original PR supersession candidates only"
            )
        if summary.get("equivalence_true") != equivalence_true:
            errors.append("summary.equivalence_true mismatch")
        if summary.get("equivalence_false") != equivalence_claim_rows - equivalence_true:
            errors.append("summary.equivalence_false mismatch")
        production_inventory = len(rows) == 325 or (
            summary.get("source_cycle5_disposition") == DEFAULT_SOURCE_LEDGER
        )
        if production_inventory and equivalence_claim_rows != EXPECTED_EQUIVALENCE_CLAIMS:
            errors.append(
                f"equivalence candidates must be {EXPECTED_EQUIVALENCE_CLAIMS} PR supersession rows, "
                f"found {equivalence_claim_rows}"
            )
        if (
            production_inventory
            and equivalence_claim_rows == EXPECTED_EQUIVALENCE_CLAIMS
            and (
                equivalence_true != EXPECTED_EQUIVALENCE_TRUE
                or equivalence_claim_rows - equivalence_true != EXPECTED_EQUIVALENCE_FALSE
            )
        ):
            errors.append(
                "fresh source proof changed the 64/8/56 equivalence summary; record the changed rows"
            )

    generation_proof = document.get("generation_proof")
    if not isinstance(generation_proof, dict):
        errors.append("generation_proof must be an object")
        return errors
    for key in _RECEIPT_KEYS:
        value = generation_proof.get(key)
        if key == "git_ref_receipts":
            if not isinstance(value, dict) or not value:
                errors.append("generation_proof missing required field: git_ref_receipts")
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(f"generation_proof missing required field: {key}")
    if generation_proof.get("receipt_kind") != RECEIPT_KIND:
        errors.append(
            "generation_proof receipt_kind must declare an unsigned content-addressed receipt"
        )
    rows_sha256 = _sha256_text(_canonical_json(rows))
    if generation_proof.get("rows_sha256") != rows_sha256:
        errors.append("generation_proof rows_sha256 does not match rows payload")
    expected_self = self_consistent_hash(
        generator_version=str(generation_proof.get("generator_version")),
        source_map_sha256=str(generation_proof.get("source_map_sha256")),
        source_ledger_sha256=str(generation_proof.get("source_ledger_sha256")),
        rows_sha256=rows_sha256,
    )
    if generation_proof.get("self_consistent_hash_sha256") != expected_self:
        errors.append("generation_proof self-consistent hash is invalid")

    if not verify_sources or not isinstance(summary, dict):
        return errors
    ledger_rel = summary.get("source_cycle5_disposition")
    map_rel = summary.get("source_reconciliation_map")
    if not isinstance(ledger_rel, str) or not isinstance(map_rel, str):
        return errors
    ledger_path = repo_root / ledger_rel
    map_path = repo_root / map_rel
    if not ledger_path.is_file():
        errors.append(f"source ledger is absent: {ledger_rel}")
        return errors
    if not map_path.is_file():
        errors.append(f"source map is absent: {map_rel}")
        return errors
    source_ledger_bytes = _canonical_source_bytes(ledger_path.read_bytes())
    source_map_bytes = _canonical_source_bytes(map_path.read_bytes())
    actual_ledger_hash = _sha256_bytes(source_ledger_bytes)
    actual_map_hash = _sha256_bytes(source_map_bytes)
    if generation_proof.get("source_ledger_sha256") != actual_ledger_hash:
        errors.append(
            "declared source_ledger_sha256 does not match the versioned source ledger bytes"
        )
    if generation_proof.get("source_map_sha256") != actual_map_hash:
        errors.append("declared source_map_sha256 does not match the versioned source map bytes")
    git_ref_receipts = generation_proof.get("git_ref_receipts")
    if not isinstance(git_ref_receipts, dict):
        return errors
    expected_receipt = content_addressed_receipt(
        generator_version=str(generation_proof.get("generator_version")),
        source_map_bytes=source_map_bytes,
        source_ledger_bytes=source_ledger_bytes,
        git_ref_receipts=git_ref_receipts,
        rows=rows,
    )
    if generation_proof.get("content_addressed_receipt_sha256") != expected_receipt:
        errors.append("generation_proof content-addressed receipt is invalid")

    resolver = git or SubprocessGitResolver(repo_root)
    historical_refs_absent = False
    for label in ("pr44", "pr46", "pp380_unique"):
        receipt = git_ref_receipts.get(label)
        if not isinstance(receipt, dict):
            errors.append(f"git_ref_receipts missing {label}")
            continue
        requested = receipt.get("requested_ref")
        declared = receipt.get("resolved_sha")
        if not isinstance(requested, str) or not isinstance(declared, str):
            errors.append(f"git_ref_receipts.{label} is incomplete")
            continue
        try:
            resolved = resolver.resolve_commit(requested)
        except ValueError:
            # Squash-integrated component heads are not present in a main-only clone.
            # Content-addressed source and receipt hashes remain the acceptance proof.
            if requested.lower() == declared.lower():
                historical_refs_absent = True
                continue
            errors.append(f"git ref is not resolvable: {requested}")
            continue
        if resolved != declared:
            errors.append(f"git_ref_receipts.{label} resolved SHA does not match requested ref")

    if errors:
        return errors
    if historical_refs_absent:
        return errors
    try:
        regenerated = generate_pp380_corrected_dispositions(
            repo_root=repo_root,
            source_ledger_path=ledger_path,
            source_map_path=map_path,
            pr44_ref=str(git_ref_receipts["pr44"]["requested_ref"]),
            pr46_ref=str(git_ref_receipts["pr46"]["requested_ref"]),
            pp380_ref=str(git_ref_receipts["pp380_unique"]["requested_ref"]),
            git=resolver,
        )
    except ValueError as error:
        errors.append(f"canonical regeneration failed: {error}")
        return errors
    if regenerated["rows"] != rows:
        errors.append("derived rows do not match canonical regeneration from versioned sources")
    if regenerated["generation_proof"]["content_addressed_receipt_sha256"] != expected_receipt:
        errors.append("content-addressed receipt does not match canonical regeneration")
    return errors
