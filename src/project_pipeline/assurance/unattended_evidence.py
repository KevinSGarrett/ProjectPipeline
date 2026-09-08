"""Validate unattended operating-loop evidence beyond summary booleans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTED_HASH_ALGORITHMS = frozenset({"sha256_raw", "sha256_canonical_file"})


def evaluate_unattended_operating_loop_evidence(
    payload: Mapping[str, Any],
    *,
    expected_sha: str,
    expected_tree: str,
    artifact_sha256: str | None = None,
) -> dict[str, Any]:
    """Accept duration evidence only when identity, algorithm, and events agree.

    Recovery is not inferred from uninterrupted duration. A summary PASS flag is
    never sufficient. ``restart_recovery`` requires an actual registered recovery
    task; otherwise recovery is NOT_PROVEN while duration may still qualify.
    """

    failures: list[str] = []
    sha = str(expected_sha or "").strip().lower()
    tree = str(expected_tree or "").strip().lower()
    bound_head = str(payload.get("bound_head") or payload.get("source_sha") or "").strip().lower()
    bound_tree = str(payload.get("bound_tree") or payload.get("source_tree") or "").strip().lower()
    if len(sha) != 40 or bound_head != sha:
        failures.append("wrong_source_sha")
    if len(tree) != 40 or bound_tree != tree:
        failures.append("wrong_source_tree")
    algorithm = str(payload.get("hash_algorithm") or "").strip()
    if algorithm not in SUPPORTED_HASH_ALGORITHMS:
        failures.append("undeclared_hash_algorithm")
    declared_digest = str(payload.get("sha256") or payload.get("artifact_sha256") or "")
    if artifact_sha256 and declared_digest and declared_digest != artifact_sha256:
        failures.append("altered_evidence_bytes")
    duration = float(payload.get("duration_hours") or payload.get("attested_elapsed_hours") or 0)
    if duration < 72:
        failures.append("duration_below_72h")
    events = payload.get("events") or payload.get("event_chain") or ()
    if not isinstance(events, (list, tuple)) or len(events) < 3:
        failures.append("incomplete_event_chain")
    else:
        previous = None
        for event in events:
            if not isinstance(event, Mapping):
                failures.append("incomplete_event_chain")
                break
            digest = str(event.get("event_sha256") or "")
            prev = event.get("prev_event_sha256")
            if not digest or prev != previous:
                failures.append("incomplete_event_chain")
                break
            previous = digest
    ownership = str(payload.get("runtime_owner") or payload.get("fence") or "")
    if payload.get("stale_ownership") is True or not ownership:
        failures.append("stale_runtime_ownership")
    recovery_registered = bool(payload.get("recovery_task_registered"))
    claimed_recovery = payload.get("restart_recovery") is True
    if claimed_recovery and not recovery_registered:
        failures.append("recovery_claimed_without_registered_task")
    recovery_state = "PROVEN" if claimed_recovery and recovery_registered else "NOT_PROVEN"
    if payload.get("result") == "PASS" and failures:
        failures.append("forged_pass_flag")
    return {
        "ok": not failures,
        "failures": failures,
        "duration_qualified": duration >= 72
        and "wrong_source_sha" not in failures
        and "wrong_source_tree" not in failures
        and "incomplete_event_chain" not in failures
        and "undeclared_hash_algorithm" not in failures
        and "altered_evidence_bytes" not in failures,
        "recovery_state": recovery_state,
        "hash_algorithm": algorithm or None,
        "uninterrupted_duration": not claimed_recovery,
    }
