from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ISSUE_DIRS = ("epics", "stories", "tasks", "subtasks")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--verification-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    verification_path = args.verification_results if args.verification_results.is_absolute() else root / args.verification_results
    output = args.output if args.output.is_absolute() else root / args.output
    verification = json.loads(verification_path.read_text(encoding="utf-8"))

    issues: list[dict] = []
    for directory in ISSUE_DIRS:
        for path in sorted((root / "jira" / directory).glob("PP-*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            item["_path"] = str(path.relative_to(root)).replace("\\", "/")
            issues.append(item)
    by_id = {item["local_id"]: item for item in issues}
    children: dict[str, list[str]] = {}
    for item in issues:
        if item.get("parent"):
            children.setdefault(item["parent"], []).append(item["local_id"])

    evidence: dict[str, dict] = {}
    for line in (root / "evidence" / "EVIDENCE_LEDGER.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            evidence[row["evidence_id"]] = row

    candidates = [item for item in issues if item["state"] == "DONE"]
    reasons: dict[str, list[dict]] = {item["local_id"]: [] for item in candidates}
    proof: dict[str, dict] = {}
    for item in candidates:
        local_id = item["local_id"]
        item_reasons = reasons[local_id]
        criterion_results: list[dict] = []
        for criterion in item.get("acceptance_criteria", []):
            verification_fact = criterion["verification"]
            command_result = verification["command_results"].get(verification_fact["command"], {"status": "NOT_RUN"})
            criterion_results.append(
                {
                    "criterion_id": criterion["criterion_id"],
                    "declared_status": verification_fact["status"],
                    "command": verification_fact["command"],
                    "fresh_command_status": command_result["status"],
                    "method": verification_fact["method"],
                    "path": verification_fact["path"],
                }
            )
            if verification_fact["status"] != "VERIFIED":
                item_reasons.append({"code": "ACCEPTANCE_NOT_VERIFIED", "criterion_id": criterion["criterion_id"], "status": verification_fact["status"]})
            if command_result["status"] != "PASS":
                item_reasons.append({"code": "FRESH_ACCEPTANCE_COMMAND_FAILED", "criterion_id": criterion["criterion_id"], "status": command_result["status"], "command": verification_fact["command"]})

        required_tests = item.get("required_tests", [])
        test_results = {test_id: verification["test_results"].get(test_id, {"status": "NOT_RUN"}) for test_id in required_tests}
        if not required_tests:
            item_reasons.append({"code": "NO_REQUIRED_TESTS"})
        for test_id, result in test_results.items():
            if result["status"] != "PASS":
                item_reasons.append({"code": "FRESH_REQUIRED_TEST_FAILED", "test_id": test_id, "status": result["status"]})

        completion_ids = item.get("completion_evidence", [])
        if not completion_ids:
            item_reasons.append({"code": "NO_COMPLETION_EVIDENCE"})
        for evidence_id in item.get("evidence_required", []):
            if evidence_id not in completion_ids:
                item_reasons.append({"code": "REQUIRED_EVIDENCE_NOT_ATTACHED", "evidence_id": evidence_id})
        evidence_results: dict[str, dict] = {}
        for evidence_id in completion_ids:
            row = evidence.get(evidence_id)
            if row is None:
                item_reasons.append({"code": "EVIDENCE_RECORD_MISSING", "evidence_id": evidence_id})
                continue
            artifact = root / row["artifact_path"]
            artifact_exists = artifact.is_file()
            hash_matches = artifact_exists and _sha256(artifact) == row["sha256"]
            evidence_results[evidence_id] = {
                "result": row["result"],
                "verification_status": row["verification_status"],
                "artifact_path": row["artifact_path"],
                "artifact_exists": artifact_exists,
                "sha256_matches": hash_matches,
                "observed_at_utc": row["observed_at_utc"],
            }
            if row["result"] != "PASS" or row["verification_status"] != "VERIFIED" or not hash_matches:
                item_reasons.append({"code": "EVIDENCE_NOT_VERIFIED_CURRENT", "evidence_id": evidence_id, "result": row["result"], "verification_status": row["verification_status"], "artifact_exists": artifact_exists, "sha256_matches": hash_matches})

        for field in ("expected_implementation_artifacts", "expected_file_locations"):
            for value in item.get(field, []):
                if not (root / value).exists():
                    item_reasons.append({"code": "EXPECTED_PATH_MISSING", "field": field, "path": value})
        if item.get("blockers"):
            item_reasons.append({"code": "UNRESOLVED_BLOCKERS", "blockers": item["blockers"]})
        proof[local_id] = {
            "acceptance_criteria": criterion_results,
            "required_tests": test_results,
            "completion_evidence": evidence_results,
        }

    actual_done = {local_id for local_id, item_reasons in reasons.items() if not item_reasons}
    changed = True
    while changed:
        changed = False
        for local_id in sorted(tuple(actual_done)):
            item = by_id[local_id]
            dependencies = set(item.get("dependencies", [])) | set(item.get("upstream_dependencies", []))
            failed_dependencies = sorted(dep for dep in dependencies if dep not in actual_done)
            failed_children = sorted(child for child in children.get(local_id, []) if child not in actual_done)
            if failed_dependencies:
                reasons[local_id].append({"code": "DEPENDENCY_NOT_VERIFIED_DONE", "local_ids": failed_dependencies})
            if failed_children:
                reasons[local_id].append({"code": "CHILD_NOT_VERIFIED_DONE", "local_ids": failed_children})
            if failed_dependencies or failed_children:
                actual_done.remove(local_id)
                changed = True

    rows: list[dict] = []
    generated = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    for item in sorted(candidates, key=lambda row: row["local_id"]):
        local_id = item["local_id"]
        passed = local_id in actual_done
        rows.append(
            {
                "schema_version": "1.0.0",
                "audit_id": "JAUD-" + hashlib.sha256((local_id + verification["generated_at_utc"]).encode()).hexdigest()[:20].upper(),
                "audited_at_utc": generated,
                "local_id": local_id,
                "remote_jira_key": item.get("remote_jira_key"),
                "authoritative_path": item["_path"],
                "initial_state": "DONE",
                "actual_verified_state": "DONE" if passed else "IN_PROGRESS",
                "verdict": "CONFIRMED_DONE" if passed else "REJECTED_DONE",
                "reasons": reasons[local_id],
                "proof": proof[local_id],
                "verification_run": verification["generated_at_utc"],
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    summary = {
        "audited": len(rows),
        "confirmed_done": sum(row["verdict"] == "CONFIRMED_DONE" for row in rows),
        "rejected_done": sum(row["verdict"] == "REJECTED_DONE" for row in rows),
        "output": str(output),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
