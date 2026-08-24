from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ISSUE_DIRS = ("epics", "stories", "tasks", "subtasks")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--remote-snapshot", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--mapping-output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    snapshot_path = (
        args.remote_snapshot if args.remote_snapshot.is_absolute() else root / args.remote_snapshot
    )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    remote_by_local = {item["local_id"]: item for item in snapshot["issues"]}
    observed_at = snapshot["observed_at_utc"]
    audited_at = datetime.now(UTC).isoformat()
    audit_rows: list[dict] = []
    mapping_rows: list[dict] = []

    for directory in ISSUE_DIRS:
        for path in sorted((root / "jira" / directory).glob("PP-*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            local_id = item["local_id"]
            remote = remote_by_local[local_id]
            previous_state = item["state"]
            previous_implementation_state = item["implementation_state"]
            previous_criteria = {
                criterion["criterion_id"]: criterion["verification"]["status"]
                for criterion in item.get("acceptance_criteria", [])
            }

            item["remote_jira_key"] = remote["remote_key"]
            item["last_observed_remote_state"] = {
                "remote_id": remote["remote_id"],
                "remote_key": remote["remote_key"],
                "status_name": remote["status_name"],
                "observed_at_utc": observed_at,
                "snapshot_id": snapshot["snapshot_id"],
            }
            item["state"] = "BACKLOG"
            item["implementation_state"] = "PLANNED_ONLY"
            item["labels"] = [
                label
                for label in item.get("labels", [])
                if label not in {"implemented", "source-implemented"}
            ]
            for criterion in item.get("acceptance_criteria", []):
                criterion["verification"]["status"] = "PLANNED"
            path.write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            if previous_state == "DONE":
                audit_rows.append(
                    {
                        "schema_version": "1.0.0",
                        "audit_id": "JAUD-"
                        + hashlib.sha256((local_id + audited_at).encode()).hexdigest()[:20].upper(),
                        "audited_at_utc": audited_at,
                        "local_id": local_id,
                        "remote_jira_key": remote["remote_key"],
                        "initial_state": previous_state,
                        "initial_implementation_state": previous_implementation_state,
                        "initial_acceptance_statuses": previous_criteria,
                        "actual_verified_state": "BACKLOG",
                        "actual_implementation_state": "PLANNED_ONLY",
                        "verdict": "REJECTED_DONE",
                        "reason_code": "TARGET_IMPLEMENTATION_REPOSITORY_NOT_ESTABLISHED",
                        "reason": (
                            "The project owner confirmed that the target implementation repository has not been set up. "
                            "Repository/runtime implementation, acceptance, test, and live-operation claims therefore "
                            "cannot truthfully satisfy Done. Historical completion evidence is retained without being "
                            "treated as current product-completion proof."
                        ),
                    }
                )
            mapping_rows.append(
                {
                    "local_id": local_id,
                    "remote_jira_key": remote["remote_key"],
                    "remote_id": remote["remote_id"],
                    "remote_status_before": remote["status_name"],
                    "authoritative_state_after": "BACKLOG",
                    "implementation_state_after": "PLANNED_ONLY",
                    "disposition": "MAPPED_AND_RESET_TO_PREIMPLEMENTATION_TRUTH",
                }
            )

    audit_output = (
        args.audit_output if args.audit_output.is_absolute() else root / args.audit_output
    )
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in audit_rows), encoding="utf-8"
    )
    mapping_output = (
        args.mapping_output if args.mapping_output.is_absolute() else root / args.mapping_output
    )
    mapping_output.parent.mkdir(parents=True, exist_ok=True)
    mapping_output.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "generated_at_utc": audited_at,
                "issue_count": len(mapping_rows),
                "done_claims_rejected": len(audit_rows),
                "mappings": mapping_rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"issues_updated": len(mapping_rows), "done_claims_rejected": len(audit_rows)}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
