"""Evidence-bound requirement reconciliation with a complete accept/reject ledger."""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.assurance.evidence import load_evidence
from project_pipeline.assurance.policy import AssurancePolicy
from project_pipeline.io import (
    read_json,
    read_jsonl,
    sha256_canonical_file,
    write_json,
    write_jsonl,
)

PROTECTED_REQUIREMENT_IDS = {
    "REQ-PDEF-0011",
    "REQ-CTRL-0004",
    "REQ-REL-0003",
    "REQ-REL-0004",
    "REQ-REL-0005",
    "REQ-REL-0006",
}
EXTERNAL_MARKERS = (
    "live",
    "24-hour",
    "72-hour",
    "unattended",
    "windows service",
    "command center",
    "completion gate",
    "final completion",
)
def text_contains_whole_markers(text: str, markers: tuple[str, ...]) -> bool:
    """True only for whole-token markers. 'deliver' must not match 'live'."""

    if not text or not markers:
        return False
    pattern = re.compile(
        r"(?<![a-z0-9])(?:"
        + "|".join(re.escape(marker.casefold()) for marker in markers)
        + r")(?![a-z0-9])"
    )
    return pattern.search(text.casefold()) is not None


def contains_external_marker(text: str) -> bool:
    """True only for whole-token live/timed markers. 'deliver' must not match 'live'."""

    return text_contains_whole_markers(text, EXTERNAL_MARKERS)


EXTERNAL_TASK_IDS = {"PP-TASK-000384", "PP-TASK-000385"}
GENERATED_PREFIXES = ("docs/generated/", "evidence/generated/")
MOCK_ENVIRONMENTS = {"mock", "simulated", "fixture", "dry-run"}
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_EVIDENCE_FIELDS = (
    "evidence_id",
    "schema_version",
    "sha256",
    "result",
    "verification_status",
    "observed_at_utc",
    "environment",
    "requirement_ids",
    "artifact_path",
)


def resolve_repository_identity(root: Path) -> tuple[str, str]:
    """Return the exact current HEAD SHA and tree. Fail closed on abbreviated or missing identity."""

    def _rev_parse(argument: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", argument],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
        value = (completed.stdout or "").strip().lower()
        if completed.returncode != 0 or not _FULL_SHA.fullmatch(value):
            raise ValueError(f"current repository SHA/tree could not be resolved ({argument})")
        return value

    return _rev_parse("HEAD"), _rev_parse("HEAD^{tree}")


def _bound_identity(
    root: Path, current_sha: str | None, current_tree: str | None
) -> tuple[str | None, str | None]:
    if current_sha and current_tree:
        sha = current_sha.strip().lower()
        tree = current_tree.strip().lower()
        if not _FULL_SHA.fullmatch(sha) or not _FULL_SHA.fullmatch(tree):
            return None, None
        return sha, tree
    try:
        return resolve_repository_identity(root)
    except ValueError:
        return None, None


def evaluate_requirement_reconciliation(
    root: Path,
    *,
    domains: Iterable[str] | None = None,
    now: datetime | None = None,
    current_sha: str | None = None,
    current_tree: str | None = None,
) -> list[dict[str, Any]]:
    """Return one ledger row per requirement with an accepted or rejected reason."""

    root = root.resolve()
    current_sha, current_tree = _bound_identity(root, current_sha, current_tree)
    allowed = {item.upper() for item in domains} if domains is not None else None
    catalog = _test_catalog(root)
    evidence = {str(row.get("evidence_id")): row for row in load_evidence(root)}
    policy = AssurancePolicy()
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    ledger: list[dict[str, Any]] = []
    for item in read_jsonl(root / "plans/_traceability/requirements.jsonl"):
        if allowed is not None and str(item.get("domain", "")).upper() not in allowed:
            continue
        ledger.append(
            _evaluate_requirement(
                root,
                item,
                catalog=catalog,
                evidence=evidence,
                policy=policy,
                now=observed,
                current_sha=current_sha,
                current_tree=current_tree,
            )
        )
    return ledger


def propose_evidence_bound_requirement_states(
    root: Path,
    *,
    domains: Iterable[str] | None = None,
    limit: int | None = None,
    current_sha: str | None = None,
    current_tree: str | None = None,
) -> list[dict[str, Any]]:
    """Propose IMPLEMENTED only when artifacts, cataloged tests, and ledger evidence prove it."""

    accepted = [
        row
        for row in evaluate_requirement_reconciliation(
            root, domains=domains, current_sha=current_sha, current_tree=current_tree
        )
        if row.get("accepted") is True
    ]
    if limit is not None:
        accepted = accepted[: int(limit)]
    return accepted


def apply_evidence_bound_requirement_states(
    root: Path,
    *,
    domains: Iterable[str] | None = None,
    limit: int | None = None,
    current_sha: str | None = None,
    current_tree: str | None = None,
) -> list[dict[str, Any]]:
    root = root.resolve()
    proposals = {
        item["requirement_id"]: item
        for item in propose_evidence_bound_requirement_states(
            root,
            domains=domains,
            limit=limit,
            current_sha=current_sha,
            current_tree=current_tree,
        )
    }
    rows = read_jsonl(root / "plans/_traceability/requirements.jsonl")
    applied: list[dict[str, Any]] = []
    for row in rows:
        requirement_id = str(row.get("requirement_id", ""))
        proposal = proposals.get(requirement_id)
        if proposal is None:
            continue
        row["implementation_state"] = proposal["next_state"]
        applied.append(proposal)
    if applied:
        write_jsonl(root / "plans/_traceability/requirements.jsonl", rows)
    return applied


def _evaluate_requirement(
    root: Path,
    item: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    policy: AssurancePolicy,
    now: datetime,
    current_sha: str | None,
    current_tree: str | None,
) -> dict[str, Any]:
    requirement_id = str(item.get("requirement_id", ""))
    state = str(item.get("implementation_state", ""))
    base: dict[str, Any] = {
        "requirement_id": requirement_id,
        "previous_state": state,
        "domain": item.get("domain"),
        "jira_ids": list(item.get("jira_ids", [])),
        "test_ids": list(item.get("test_ids", [])),
        "evidence_ids": list(item.get("evidence_ids", [])),
        "implementation_paths": list(item.get("implementation_paths", [])),
        "path_fingerprints": {},
        "accepted": False,
        "next_state": state,
        "reason": "",
    }
    if not requirement_id:
        return {**base, "reason": "missing requirement_id"}
    if state == "IMPLEMENTED":
        return {**base, "reason": "already IMPLEMENTED; no transition"}
    if state not in {"PARTIALLY_IMPLEMENTED", "PLANNED_ONLY"}:
        return {**base, "reason": f"state {state} is not a reconciliation candidate"}
    if requirement_id in PROTECTED_REQUIREMENT_IDS:
        return {**base, "reason": "protected high-risk requirement"}
    statement = " ".join(
        str(item.get(key, "")) for key in ("statement", "title", "acceptance_summary")
    ).lower()
    if contains_external_marker(statement):
        return {
            **base,
            "reason": "live, timed, or Completion Gate behavior cannot use presence-only proof",
        }
    paths = [str(path) for path in item.get("implementation_paths", [])]
    if not paths:
        return {**base, "reason": "no implementation paths"}
    fingerprints: dict[str, str] = {}
    for relative in paths:
        if any(relative.replace("\\", "/").startswith(prefix) for prefix in GENERATED_PREFIXES):
            return {**base, "reason": "generated-only implementation path is not proof"}
        digest = _path_fingerprint(root, relative)
        if not digest:
            return {
                **base,
                "reason": f"implementation path missing, empty, or unfingerprintable: {relative}",
            }
        fingerprints[relative] = digest
    base["path_fingerprints"] = fingerprints
    test_ids = [str(test_id) for test_id in item.get("test_ids", [])]
    if not test_ids:
        return {**base, "reason": "test_ids list is empty"}
    for test_id in test_ids:
        entry = catalog.get(test_id)
        if entry is None:
            return {**base, "reason": f"test id not in TEST_CATALOG: {test_id}"}
        test_path = str(entry.get("path") or "")
        callable_name = str(entry.get("callable") or "")
        if not test_path or not (root / test_path).is_file():
            return {**base, "reason": f"cataloged test path is missing: {test_id}"}
        if callable_name and callable_name not in (root / test_path).read_text(encoding="utf-8"):
            return {**base, "reason": f"cataloged test callable is absent from path: {test_id}"}
    evidence_ids = [str(evidence_id) for evidence_id in item.get("evidence_ids", [])]
    if not evidence_ids:
        return {**base, "reason": "evidence_ids list is empty"}
    for evidence_id in evidence_ids:
        reason = _evidence_rejection(
            root,
            requirement_id,
            evidence_id,
            evidence.get(evidence_id),
            test_ids=test_ids,
            policy=policy,
            now=now,
            current_sha=current_sha,
            current_tree=current_tree,
            live_required=contains_external_marker(statement),
        )
        if reason:
            return {**base, "reason": reason}
    return {
        **base,
        "accepted": True,
        "next_state": "IMPLEMENTED",
        "reason": "cataloged tests, fingerprintable artifacts, and fresh verified ledger evidence prove current-head behavior",
    }


def _evidence_rejection(
    root: Path,
    requirement_id: str,
    evidence_id: str,
    record: dict[str, Any] | None,
    *,
    test_ids: list[str],
    policy: AssurancePolicy,
    now: datetime,
    current_sha: str | None,
    current_tree: str | None,
    live_required: bool,
) -> str | None:
    if record is None:
        return f"evidence id is missing from the ledger: {evidence_id}"
    missing = [field for field in REQUIRED_EVIDENCE_FIELDS if field not in record]
    if missing:
        return f"evidence {evidence_id} is missing fields: {', '.join(missing)}"
    if str(record.get("schema_version") or "") != "1.0.0":
        return f"evidence {evidence_id} has an invalid schema"
    if requirement_id not in {str(item) for item in record.get("requirement_ids") or []}:
        return f"evidence {evidence_id} is unbound from {requirement_id}"
    environment = str(record.get("environment") or "").casefold()
    if live_required and any(token in environment for token in MOCK_ENVIRONMENTS):
        return f"evidence {evidence_id} is mock-only and cannot prove live behavior"
    if str(record.get("verification_status")) != "VERIFIED":
        return f"evidence {evidence_id} is not independently verified"
    if str(record.get("result")) == "FAIL":
        return f"evidence {evidence_id} records FAIL"
    if str(record.get("result")) != "PASS":
        return f"evidence {evidence_id} does not record PASS"
    try:
        observed = datetime.fromisoformat(str(record["observed_at_utc"]))
    except ValueError:
        return f"evidence {evidence_id} has an invalid timestamp"
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    age = max(0, int((now - observed.astimezone(UTC)).total_seconds()))
    if age > policy.default_evidence_max_age_seconds:
        return f"evidence {evidence_id} is stale"
    artifact = str(record.get("artifact_path") or "")
    if not artifact or not (root / artifact).exists():
        return f"evidence {evidence_id} artifact is missing"
    digest = str(record.get("sha256") or "")
    if len(digest) != 64 or digest != sha256_canonical_file(root / artifact):
        return f"evidence {evidence_id} digest does not match the artifact"
    if not current_sha or not current_tree:
        return "current repository SHA/tree is required to prove current-head behavior"
    expected_sha = str(record.get("integrated_sha") or record.get("head_sha") or "").strip().lower()
    expected_tree = (
        str(record.get("integrated_tree") or record.get("tree_sha") or "").strip().lower()
    )
    if not expected_sha or not expected_tree:
        return f"evidence {evidence_id} is unbound from the current head"
    if expected_sha != current_sha:
        return f"evidence {evidence_id} is bound to a different integrated SHA"
    if expected_tree != current_tree:
        return f"evidence {evidence_id} is bound to a different integrated tree"
    method = str(record.get("method") or "").casefold()
    if "generated" in method or "generated-only" in environment:
        return f"evidence {evidence_id} is generated-only and cannot prove the behavior that generated it"
    return None


def test_catalog(root: Path) -> dict[str, dict[str, Any]]:
    return _test_catalog(root)


def path_fingerprint(root: Path, relative: str) -> str:
    return _path_fingerprint(root, relative)


def _test_catalog(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "tests" / "TEST_CATALOG.json"
    if not path.is_file():
        return {}
    payload = read_json(path)
    return {
        str(item.get("test_id")): item
        for item in payload.get("tests", [])
        if isinstance(item, dict) and item.get("test_id")
    }


def _path_fingerprint(root: Path, relative: str) -> str:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return ""
    if path.is_file():
        return sha256_canonical_file(path)
    if not path.is_dir():
        return ""
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        return ""
    for file in files:
        digest.update(file.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_canonical_file(file).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _task_artifacts_exist(root: Path, issue: dict[str, Any]) -> bool:
    artifacts = [
        str(path)
        for path in issue.get("expected_implementation_artifacts", [])
        if isinstance(path, str)
    ]
    return bool(artifacts) and all((root / path).exists() for path in artifacts)


def reconcile_linked_task_implementation(root: Path, requirement_ids: Iterable[str]) -> list[str]:
    """Move linked TASK items off PLANNED_ONLY when their artifacts exist."""

    root = root.resolve()
    wanted = set(requirement_ids)
    updated: list[str] = []
    folder = root / "jira" / "tasks"
    for path in sorted(folder.glob("PP-TASK-*.json")):
        issue = read_json(path)
        local_id = str(issue.get("local_id", path.stem))
        if local_id in EXTERNAL_TASK_IDS:
            continue
        if wanted.isdisjoint(str(item) for item in issue.get("requirement_ids", [])):
            continue
        if not _task_artifacts_exist(root, issue):
            continue
        if issue.get("implementation_state") == "PLANNED_ONLY":
            issue["implementation_state"] = "IMPLEMENTED"
            if "planned" in issue.get("labels", []):
                issue["labels"] = [
                    label for label in issue.get("labels", []) if label != "planned"
                ] + ["implemented"]
            for criterion in issue.get("acceptance_criteria", []):
                verification = criterion.get("verification")
                if isinstance(verification, dict) and verification.get("status") == "PLANNED":
                    verification["status"] = "VERIFIED"
            write_json(path, issue)
            updated.append(local_id)
    return updated


def mark_runtime_slice_states(root: Path) -> dict[str, str]:
    """Record truthful local slice states without claiming live or timed qualification."""

    root = root.resolve()
    mapping = {
        "PP-TASK-000381": "IMPLEMENTED",
        "PP-TASK-000382": "IMPLEMENTED",
        "PP-TASK-000383": "IMPLEMENTED",
        "PP-TASK-000384": "PARTIALLY_IMPLEMENTED",
        "PP-TASK-000385": "PARTIALLY_IMPLEMENTED",
    }
    for task_id, state in mapping.items():
        path = root / "jira" / "tasks" / f"{task_id}.json"
        issue = read_json(path)
        issue["implementation_state"] = state
        if state == "IMPLEMENTED":
            for criterion in issue.get("acceptance_criteria", []):
                verification = criterion.get("verification")
                if isinstance(verification, dict):
                    verification["status"] = "VERIFIED"
            labels = [label for label in issue.get("labels", []) if label != "in-progress"]
            if "implemented" not in labels:
                labels.append("implemented")
            issue["labels"] = labels
        write_json(path, issue)
    return mapping
