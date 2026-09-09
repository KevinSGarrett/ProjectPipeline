"""Machine-readable Cycle 18 acceptance and fleet admission preconditions.

Prose blockers are not admission. Remote placement requires an independent
C18 disposition, matching source identity, and fresh enrolled hosts.
Local ``machine:local`` behavior stays available without this record.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ACCEPTED_C18_DISPOSITIONS = frozenset({"PM_ACCEPTED", "PM_ACCEPTED_WITH_FOLLOWUP"})
PRIMARY_CONTROL_MACHINE_ID = "PRIMARY-CODEX-WORKSTATION"
GIT_IDENTITY_LENGTH = 40


def observation_admission_record(
    existing: Mapping[str, Any],
    *,
    hosts: Mapping[str, Any],
    source_sha: str,
    source_tree: str,
) -> dict[str, Any]:
    """Bind observed hosts without minting a Cycle 18 PM disposition."""

    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "hosts": dict(hosts),
        "source_sha": source_sha,
        "source_tree": source_tree,
    }
    for key in ("c18_disposition", "reviewer_id", "implementer_id"):
        if existing.get(key):
            record[key] = existing[key]
    return record


def write_admission_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_admission_record(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _identity_matches(actual: object, expected: str) -> bool:
    token = str(actual or "").strip().lower()
    return token == expected.strip().lower() and len(token) == GIT_IDENTITY_LENGTH


MAX_MEASUREMENT_AGE_SECONDS = 7200


def _measurement_ok(host: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    kind = str(host.get("observation_kind") or "")
    if kind != "MEASURED":
        return False
    raw = host.get("observed_at_utc") or host.get("measured_at_utc")
    if not raw:
        return False
    observed = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if observed.year <= 1970 or observed > current + timedelta(seconds=300):
        return False
    if (current - observed).total_seconds() > MAX_MEASUREMENT_AGE_SECONDS:
        return False
    return str(host.get("freshness") or "unknown") == "fresh"


def _remote_host_failures(
    hosts: Mapping[str, Any], *, now: datetime | None = None
) -> tuple[str, ...]:
    failures: list[str] = []
    enrolled_fresh = 0
    denied: list[str] = []
    for machine_id, host in hosts.items():
        if not isinstance(host, Mapping) or str(machine_id) == PRIMARY_CONTROL_MACHINE_ID:
            continue
        state = str(host.get("state") or "")
        freshness = str(host.get("freshness") or "unknown")
        if state == "READY" and _measurement_ok(host, now=now):
            enrolled_fresh += 1
            continue
        denied.append(f"remote_denied:{machine_id}:{state or 'UNDECLARED'}:{freshness}")
    if enrolled_fresh < 1:
        failures.extend(denied)
        failures.append("no_enrolled_fresh_worker")
        return tuple(failures)
    return ()


def chosen_host_admitted(
    record: Mapping[str, Any] | None,
    machine_id: str,
    *,
    expected_sha: str,
    expected_tree: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    gate = evaluate_admission(
        record, expected_sha=expected_sha, expected_tree=expected_tree, now=now
    )
    if record is None or not gate["c18_accepted"]:
        return {"ok": False, "failures": gate["failures"]}
    hosts = record.get("hosts") if isinstance(record.get("hosts"), Mapping) else {}
    host = hosts.get(machine_id)
    if not isinstance(host, Mapping):
        return {"ok": False, "failures": (f"unchosen_host:{machine_id}",)}
    state = str(host.get("state") or "")
    freshness = str(host.get("freshness") or "unknown")
    if state != "READY" or not _measurement_ok(host, now=now):
        return {
            "ok": False,
            "failures": (f"remote_denied:{machine_id}:{state or 'UNDECLARED'}:{freshness}",),
        }
    sha_ok = _identity_matches(record.get("source_sha"), expected_sha)
    tree_ok = _identity_matches(record.get("source_tree"), expected_tree)
    if not sha_ok or not tree_ok:
        return {"ok": False, "failures": gate["failures"]}
    return {"ok": True, "failures": ()}


def evaluate_admission(
    record: Mapping[str, Any] | None,
    *,
    expected_sha: str,
    expected_tree: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if record is None:
        return {
            "ok": False,
            "c18_accepted": False,
            "remote_ok": False,
            "failures": ("admission_record_missing",),
        }

    failures: list[str] = []
    disposition = str(record.get("c18_disposition") or "")
    reviewer = str(record.get("reviewer_id") or "")
    implementer = str(record.get("implementer_id") or "")
    hosts = record.get("hosts")
    if not isinstance(hosts, Mapping):
        hosts = {}

    disposition_ok = disposition in ACCEPTED_C18_DISPOSITIONS
    independent = bool(reviewer) and reviewer != implementer
    sha_ok = _identity_matches(record.get("source_sha"), expected_sha)
    tree_ok = _identity_matches(record.get("source_tree"), expected_tree)
    if not disposition_ok:
        failures.append("c18_acceptance_missing")
    if not independent:
        failures.append("independent_reviewer_missing")
    if not sha_ok:
        failures.append("wrong_source_sha")
    if not tree_ok:
        failures.append("wrong_source_tree")

    c18_accepted = disposition_ok and independent
    if c18_accepted:
        host_failures = _remote_host_failures(hosts, now=now)
        failures.extend(host_failures)
        remote_ok = not host_failures and sha_ok and tree_ok
    else:
        remote_ok = False

    return {
        "ok": not failures,
        "c18_accepted": c18_accepted,
        "remote_ok": remote_ok,
        "failures": tuple(failures),
        "disposition": disposition or None,
        "reviewer_id": reviewer or None,
    }
