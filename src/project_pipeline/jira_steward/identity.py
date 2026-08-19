"""Derive and match Jira local IDs from structured fields, labels, and descriptions."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from project_pipeline.ids import ISSUE_ID

LOCAL_ID_LABEL_PREFIX = "pp-local-id:"
CANONICAL_LOCAL_ID = re.compile(ISSUE_ID.pattern.removeprefix("^").removesuffix("$"))
EXPLICIT_LOCAL_ID_LINE = re.compile(
    r"(?m)^\s*LOCAL\s+ID\s*:\s*(PP-(?:EPIC|STORY|TASK|SUBTASK|BUG|SPIKE)-[0-9]{6})"
)
IdentityStatus = Literal["UNIQUE", "MISSING", "CONFLICT"]
ParityStatus = Literal["NO_DIFFERENCE", "RECONCILIATION_REQUIRED", "FAIL_CLOSED"]


def extract_canonical_local_ids(*texts: str | None) -> tuple[str, ...]:
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        normalized = text.replace("_", "-").upper()
        for match in CANONICAL_LOCAL_ID.finditer(normalized):
            found.add(match.group(0))
    return tuple(sorted(found))


@dataclass(frozen=True, slots=True)
class IdentityDerivation:
    status: IdentityStatus
    local_id: str | None
    candidates: tuple[str, ...]
    sources: tuple[str, ...]

    def fail_closed(self) -> bool:
        return self.status == "CONFLICT"


def _ids_from_texts(*texts: str | None) -> tuple[str, ...]:
    return extract_canonical_local_ids(*texts)


def derive_remote_local_id(
    *,
    labels: Iterable[str] = (),
    description: str = "",
    fields: Mapping[str, Any] | None = None,
    local_id_field: str | None = None,
) -> IdentityDerivation:
    """Return a unique canonical local ID or fail closed on conflicts.

    Parent IDs in descriptions are ignored. Structured field and ``pp-local-id:``
    labels outrank a bare label or a ``Local ID:`` description line. Distinct IDs
    from any structured source fail closed and must not be written.
    """

    candidates: dict[str, set[str]] = defaultdict(set)
    payload = fields or {}
    if local_id_field:
        raw = payload.get(local_id_field)
        if raw:
            for item in _ids_from_texts(str(raw)):
                candidates[item].add(f"field:{local_id_field}")
    prefix_ids: set[str] = set()
    exact_label_ids: set[str] = set()
    for label in labels:
        text = str(label).strip()
        if not text:
            continue
        if text.casefold().startswith(LOCAL_ID_LABEL_PREFIX):
            marked = text[len(LOCAL_ID_LABEL_PREFIX) :]
            for item in _ids_from_texts(marked):
                prefix_ids.add(item)
                candidates[item].add("label:pp-local-id")
            continue
        normalized = text.replace("_", "-").upper()
        if CANONICAL_LOCAL_ID.fullmatch(normalized):
            exact_label_ids.add(normalized)
            candidates[normalized].add("label")
    description_ids = {
        match.group(1)
        for match in EXPLICIT_LOCAL_ID_LINE.finditer(description.replace("_", "-").upper())
    }
    for item in description_ids:
        candidates[item].add("description:local-id")
    prioritized = (prefix_ids, description_ids, exact_label_ids)
    field_ids = {
        item
        for item, sources in candidates.items()
        if any(source.startswith("field:") for source in sources)
    }
    structured = [group for group in (field_ids, *prioritized) if group]
    unique_structured = {next(iter(group)) for group in structured if len(group) == 1}
    conflicted = {item for group in structured if len(group) > 1 for item in group}
    if conflicted or len(unique_structured) > 1:
        return IdentityDerivation(
            status="CONFLICT",
            local_id=None,
            candidates=tuple(sorted(set(candidates) | conflicted | unique_structured)),
            sources=tuple(sorted({source for group in candidates.values() for source in group})),
        )
    unique = tuple(sorted(candidates))
    if len(unique) == 1:
        return IdentityDerivation(
            status="UNIQUE",
            local_id=unique[0],
            candidates=unique,
            sources=tuple(sorted(candidates[unique[0]])),
        )
    if len(unique_structured) == 1:
        local_id = next(iter(unique_structured))
        return IdentityDerivation(
            status="UNIQUE",
            local_id=local_id,
            candidates=(local_id,),
            sources=tuple(sorted(candidates[local_id])),
        )
    return IdentityDerivation(status="MISSING", local_id=None, candidates=(), sources=())


def classify_identity_by_remote_key_only(
    *,
    local_remote_key: str | None,
    remote_key: str,
) -> ParityStatus:
    """Legacy key-only matcher. Misses unique label/description identity."""

    if local_remote_key and local_remote_key == remote_key:
        return "NO_DIFFERENCE"
    return "NO_DIFFERENCE"


@dataclass(frozen=True, slots=True)
class IdentityMatch:
    local_id: str
    remote_key: str
    local_remote_key: str | None
    status: ParityStatus
    reason: str


@dataclass(frozen=True, slots=True)
class IdentityParityResult:
    status: ParityStatus
    matches: tuple[IdentityMatch, ...]
    unmatched_local_ids: tuple[str, ...]
    unmatched_remote_keys: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def requires_reconciliation(self) -> bool:
        return self.status == "RECONCILIATION_REQUIRED"

    @property
    def fail_closed(self) -> bool:
        return self.status == "FAIL_CLOSED"


def classify_identity_parity(
    *,
    local_issues: Iterable[Mapping[str, Any]],
    remote_issues: Iterable[Mapping[str, Any]],
) -> IdentityParityResult:
    """Compare the same snapshot's exact issue set using unique local-ID identity."""

    local_by_id: dict[str, Mapping[str, Any]] = {}
    for issue in local_issues:
        local_id = str(issue.get("local_id") or "")
        if not local_id:
            continue
        if local_id in local_by_id:
            return IdentityParityResult(
                status="FAIL_CLOSED",
                matches=(),
                unmatched_local_ids=(),
                unmatched_remote_keys=(),
                reasons=(f"duplicate local issue identity: {local_id}",),
            )
        local_by_id[local_id] = issue

    remote_by_local: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    unmatched_remote: list[str] = []
    conflicts: list[str] = []
    for remote in remote_issues:
        derivation = derive_remote_local_id(
            labels=tuple(str(item) for item in remote.get("labels", []) or ()),
            description=str(remote.get("description_text") or remote.get("description") or ""),
            fields=remote.get("fields") if isinstance(remote.get("fields"), Mapping) else {},
            local_id_field=str(remote.get("local_id_field"))
            if remote.get("local_id_field")
            else None,
        )
        declared = remote.get("local_id")
        if declared:
            declared_ids = extract_canonical_local_ids(str(declared))
            if derivation.status == "MISSING" and len(declared_ids) == 1:
                derivation = IdentityDerivation(
                    status="UNIQUE",
                    local_id=declared_ids[0],
                    candidates=declared_ids,
                    sources=("declared",),
                )
            elif derivation.local_id and declared_ids and derivation.local_id not in declared_ids:
                conflicts.append(
                    f"remote {remote.get('remote_key')} declares conflicting local IDs "
                    f"{derivation.local_id} vs {', '.join(declared_ids)}"
                )
                continue
        if derivation.status == "CONFLICT":
            conflicts.append(
                f"remote {remote.get('remote_key')} has conflicting local IDs: "
                f"{', '.join(derivation.candidates)}"
            )
            continue
        if derivation.status == "MISSING" or derivation.local_id is None:
            unmatched_remote.append(str(remote.get("remote_key") or "unknown"))
            continue
        remote_by_local[derivation.local_id].append(remote)

    if conflicts:
        return IdentityParityResult(
            status="FAIL_CLOSED",
            matches=(),
            unmatched_local_ids=(),
            unmatched_remote_keys=(),
            reasons=tuple(conflicts),
        )

    matches: list[IdentityMatch] = []
    reasons: list[str] = []
    matched_local: set[str] = set()
    for local_id, remotes in sorted(remote_by_local.items()):
        keys = [str(item.get("remote_key") or "") for item in remotes]
        if len(remotes) != 1:
            return IdentityParityResult(
                status="FAIL_CLOSED",
                matches=(),
                unmatched_local_ids=(),
                unmatched_remote_keys=(),
                reasons=(f"duplicate remote mapping for {local_id}: {', '.join(keys)}",),
            )
        remote = remotes[0]
        local = local_by_id.get(local_id)
        if local is None:
            unmatched_remote.append(str(remote.get("remote_key") or ""))
            reasons.append(
                f"unique remote {remote.get('remote_key')} identifies missing local {local_id}"
            )
            continue
        matched_local.add(local_id)
        local_key = local.get("remote_jira_key")
        remote_key = str(remote.get("remote_key") or "")
        if not local_key:
            matches.append(
                IdentityMatch(
                    local_id=local_id,
                    remote_key=remote_key,
                    local_remote_key=None,
                    status="RECONCILIATION_REQUIRED",
                    reason=(
                        f"missing local remote key with a unique remote local-ID match {remote_key}"
                    ),
                )
            )
            reasons.append(
                f"{local_id} uniquely matches remote {remote_key} but remote_jira_key is null"
            )
            continue
        if str(local_key) != remote_key:
            return IdentityParityResult(
                status="FAIL_CLOSED",
                matches=tuple(matches),
                unmatched_local_ids=(),
                unmatched_remote_keys=(),
                reasons=(
                    f"{local_id} local key {local_key} conflicts with unique remote {remote_key}",
                ),
            )
        matches.append(
            IdentityMatch(
                local_id=local_id,
                remote_key=remote_key,
                local_remote_key=str(local_key),
                status="NO_DIFFERENCE",
                reason="local remote key matches unique remote identity",
            )
        )

    unmatched_local = tuple(sorted(set(local_by_id) - matched_local))
    status: ParityStatus = "NO_DIFFERENCE"
    if any(item.status == "RECONCILIATION_REQUIRED" for item in matches) or reasons:
        status = "RECONCILIATION_REQUIRED"
    return IdentityParityResult(
        status=status,
        matches=tuple(matches),
        unmatched_local_ids=unmatched_local,
        unmatched_remote_keys=tuple(sorted(set(unmatched_remote))),
        reasons=tuple(reasons),
    )


def classify_status_parity(
    *,
    local_issues: Iterable[Mapping[str, Any]],
    remote_issues: Iterable[Mapping[str, Any]],
    snapshot_id: str,
    expected_snapshot_id: str,
) -> ParityStatus:
    """Status parity is defined only on one complete snapshot and exact issue set."""

    if snapshot_id != expected_snapshot_id:
        return "FAIL_CLOSED"
    identity = classify_identity_parity(local_issues=local_issues, remote_issues=remote_issues)
    if identity.fail_closed:
        return "FAIL_CLOSED"
    remote_by_key = {str(item.get("remote_key")): item for item in remote_issues}
    local_keys = {
        str(item.get("remote_jira_key")) for item in local_issues if item.get("remote_jira_key")
    }
    if set(remote_by_key) != local_keys and identity.requires_reconciliation:
        return "RECONCILIATION_REQUIRED"
    if set(remote_by_key) != local_keys:
        return "RECONCILIATION_REQUIRED"
    return identity.status


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None
