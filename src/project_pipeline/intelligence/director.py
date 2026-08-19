from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from project_pipeline.control.authority import evaluate_recommendation_authority
from project_pipeline.domain.base import DomainModel

PORTFOLIO_ROLES = (
    "lightweight_planning",
    "strong_generalist",
    "visual_review",
    "heavy_review",
)
TRUST_ORDER = {
    "GOVERNING": 5,
    "AUTHORITATIVE": 4,
    "SOURCE_CONTROLLED": 3,
    "VERIFIED_EXTERNAL": 2,
    "UNTRUSTED_REPOSITORY": 1,
    "UNTRUSTED_EXTERNAL": 0,
}
AUTHORITY_TRUST = frozenset({"GOVERNING", "AUTHORITATIVE"})
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS director_records (
    record_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS director_journal (
    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);
"""


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _now() -> datetime:
    return datetime.now(UTC)


class PortfolioAssignment(DomainModel):
    role: str
    assigned: bool
    optional: bool
    reason: str
    production_routing_authorized: Literal[False] = False
    advisory_only: Literal[True] = True


class PortfolioDecision(DomainModel):
    assignments: tuple[PortfolioAssignment, ...]
    resource_class: str
    paid_dependency_required: Literal[False] = False
    user_action_required: Literal[False] = False


class ContextItemDecision(DomainModel):
    item_id: str
    included: bool
    trust: str
    freshness: str
    chars: int
    reason: str


class BoundedContext(DomainModel):
    items: tuple[ContextItemDecision, ...]
    total_chars: int
    omitted: tuple[str, ...]
    ok: bool
    advisory_only: Literal[True] = True
    user_action_required: Literal[False] = False


class ManagerRecommendation(DomainModel):
    recommendation_id: str
    summary: str
    citations: tuple[str, ...]
    may_apply: bool
    disposition: str
    fabricates_authority: Literal[False] = False
    user_action_required: Literal[False] = False


class ArchitectureDecision(DomainModel):
    decision_id: str
    accepted: bool
    citations: tuple[str, ...]
    freshness: str
    trust: str
    reason: str
    model_output_authoritative: Literal[False] = False
    user_action_required: Literal[False] = False


class DirectorStoreError(ValueError):
    """Raised when a director record cannot be stored or replayed safely."""


class DirectorStore:
    """Out-of-tree persisted director decisions. Records are immutable after insert."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        self._connection().executescript(SCHEMA_SQL)
        self.replay_journal()

    @classmethod
    def open(cls, root: Path) -> DirectorStore:
        return cls(
            root.resolve() / ".local" / "state" / "director_intelligence" / "director.sqlite3"
        )

    def _connection(self) -> sqlite3.Connection:
        existing = getattr(self._local, "db", None)
        if isinstance(existing, sqlite3.Connection):
            return existing
        connection = sqlite3.connect(
            self.database,
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        self._local.db = connection
        return connection

    def close(self) -> None:
        with self._lock:
            connection = getattr(self._local, "db", None)
            if connection is not None:
                connection.close()
                self._local.db = None

    def put(self, kind: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = _canonical(payload)
        now = _now().isoformat()
        with self._lock:
            db = self._connection()
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT payload_json FROM director_records WHERE record_id = ?",
                    (record_id,),
                ).fetchone()
                if existing is not None:
                    if existing["payload_json"] != encoded:
                        raise DirectorStoreError(f"conflicting replay for {record_id}")
                    db.execute("COMMIT")
                    return payload
                db.execute(
                    """
                    INSERT INTO director_journal(record_id, kind, operation, payload_json, recorded_at_utc)
                    VALUES (?, ?, 'put', ?, ?)
                    """,
                    (record_id, kind, encoded, now),
                )
                db.execute(
                    """
                    INSERT INTO director_records(record_id, kind, recorded_at_utc, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (record_id, kind, now, encoded),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return payload

    def replay_journal(self) -> int:
        with self._lock:
            db = self._connection()
            rows = db.execute(
                "SELECT record_id, kind, payload_json FROM director_journal ORDER BY journal_id"
            ).fetchall()
            restored = 0
            for row in rows:
                existing = db.execute(
                    "SELECT payload_json FROM director_records WHERE record_id = ?",
                    (row["record_id"],),
                ).fetchone()
                if existing is None:
                    db.execute("BEGIN IMMEDIATE")
                    try:
                        db.execute(
                            """
                            INSERT INTO director_records(record_id, kind, recorded_at_utc, payload_json)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                row["record_id"],
                                row["kind"],
                                _now().isoformat(),
                                row["payload_json"],
                            ),
                        )
                        db.execute("COMMIT")
                    except Exception:
                        db.execute("ROLLBACK")
                        raise
                    restored += 1
                elif existing["payload_json"] != row["payload_json"]:
                    raise DirectorStoreError(f"journal conflicts with store for {row['record_id']}")
            return restored

    def list_kind(self, kind: str) -> list[dict[str, Any]]:
        with self._lock:
            db = self._connection()
            rows = db.execute(
                """
                SELECT record_id, payload_json FROM director_records
                WHERE kind = ? ORDER BY recorded_at_utc ASC, record_id ASC
                """,
                (kind,),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]


def assign_local_portfolio(resources: dict[str, Any]) -> PortfolioDecision:
    ram_gb = int(resources.get("ram_gb") or 0)
    vram_gb = int(resources.get("vram_gb") or 0)
    cpu_only = bool(resources.get("cpu_only"))
    assignments: list[PortfolioAssignment] = []
    thresholds = {
        "lightweight_planning": (8, 0, False),
        "strong_generalist": (16, 0, False),
        "visual_review": (16, 8, False),
        "heavy_review": (32, 12, True),
    }
    if ram_gb >= 32 and vram_gb >= 12 and not cpu_only:
        resource_class = "workstation-gpu"
    elif ram_gb >= 16:
        resource_class = "local-standard"
    elif ram_gb >= 8:
        resource_class = "local-light"
    else:
        resource_class = "insufficient"
    for role in PORTFOLIO_ROLES:
        min_ram, min_vram, optional = thresholds[role]
        assigned = ram_gb >= min_ram and (min_vram == 0 or (vram_gb >= min_vram and not cpu_only))
        if assigned:
            reason = f"{role} matched {resource_class} resources"
        elif optional:
            reason = f"{role} remains optional until RAM>={min_ram} and VRAM>={min_vram}"
        else:
            reason = f"{role} unavailable on {resource_class}; not remapped to an unqualified role"
        assignments.append(
            PortfolioAssignment(
                role=role,
                assigned=assigned,
                optional=optional,
                reason=reason,
            )
        )
    return PortfolioDecision(assignments=tuple(assignments), resource_class=resource_class)


def bound_local_context(
    items: list[dict[str, Any]],
    *,
    max_chars: int,
    max_items: int,
    max_age_seconds: int,
    now: datetime | None = None,
) -> BoundedContext:
    current = now or _now()
    decisions: list[ContextItemDecision] = []
    omitted: list[str] = []
    total = 0
    ok = True
    for raw in items:
        item_id = str(raw.get("item_id") or "")
        content = str(raw.get("content") or "")
        trust = str(raw.get("trust") or "UNTRUSTED_EXTERNAL")
        required = bool(raw.get("required"))
        kind = str(raw.get("kind") or "OTHER")
        observed = raw.get("observed_at_utc")
        freshness = "UNKNOWN"
        if observed:
            stamp = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            freshness = (
                "CURRENT" if (current - stamp) <= timedelta(seconds=max_age_seconds) else "STALE"
            )
        reason = "included under local context budget"
        include = True
        if not item_id:
            include = False
            reason = "item_id required"
        elif freshness == "STALE" and required:
            include = False
            reason = "required stale context fail-closed"
            ok = False
        elif trust not in TRUST_ORDER:
            include = False
            reason = "unknown trust class fail-closed"
            ok = False
        elif kind == "INSTRUCTION" and trust not in AUTHORITY_TRUST:
            include = False
            reason = "untrusted instructions cannot enter local context"
            ok = False
        elif len(decisions) >= max_items or total + len(content) > max_chars:
            include = False
            reason = "local context budget exhausted"
            if required:
                ok = False
        if include:
            total += len(content)
            decisions.append(
                ContextItemDecision(
                    item_id=item_id,
                    included=True,
                    trust=trust,
                    freshness=freshness,
                    chars=len(content),
                    reason=reason,
                )
            )
        else:
            omitted.append(item_id or "unknown-item")
            decisions.append(
                ContextItemDecision(
                    item_id=item_id or "unknown-item",
                    included=False,
                    trust=trust,
                    freshness=freshness,
                    chars=len(content),
                    reason=reason,
                )
            )
    return BoundedContext(
        items=tuple(decisions),
        total_chars=total,
        omitted=tuple(omitted),
        ok=ok,
    )


def recommend_progress(state: dict[str, Any]) -> ManagerRecommendation:
    citations = tuple(
        key for key in ("progress", "risk", "blockers", "scope", "sequencing") if key in state
    )
    missing = tuple(
        key for key in ("progress", "risk", "blockers", "scope", "sequencing") if key not in state
    )
    recommendation_id = _digest("pm", _canonical(state))[:32]
    if missing:
        authority = evaluate_recommendation_authority(recommendation_id, conflicts_with_policy=True)
        return ManagerRecommendation(
            recommendation_id=recommendation_id,
            summary="recommendation withheld; durable control fields are incomplete",
            citations=citations,
            may_apply=False,
            disposition=authority.disposition.value,
        )
    blockers = list(state.get("blockers") or [])
    if blockers:
        summary = (
            f"hold new implementation until blockers are reduced: {', '.join(map(str, blockers))}"
        )
    else:
        summary = (
            f"continue sequenced work at progress={state.get('progress')} risk={state.get('risk')}"
        )
    authority = evaluate_recommendation_authority(
        recommendation_id,
        conflicts_with_canonical_plan=bool(state.get("conflicts_with_canonical_plan")),
        conflicts_with_policy=bool(state.get("conflicts_with_policy")),
    )
    return ManagerRecommendation(
        recommendation_id=recommendation_id,
        summary=summary,
        citations=citations,
        may_apply=authority.may_apply,
        disposition=authority.disposition.value,
    )


def evaluate_architecture_change(change: dict[str, Any]) -> ArchitectureDecision:
    citations = tuple(str(item) for item in (change.get("citations") or ()) if str(item).strip())
    freshness = str(change.get("freshness") or "UNKNOWN")
    trust = str(change.get("trust") or "UNTRUSTED_EXTERNAL")
    decision_id = _digest(
        "arch", _canonical({"citations": citations, "change": change.get("change_id")})
    )
    if not citations:
        return ArchitectureDecision(
            decision_id=decision_id,
            accepted=False,
            citations=(),
            freshness=freshness,
            trust=trust,
            reason="architectural acceptance requires durable citations",
        )
    if freshness != "CURRENT":
        return ArchitectureDecision(
            decision_id=decision_id,
            accepted=False,
            citations=citations,
            freshness=freshness,
            trust=trust,
            reason="stale or unknown design evidence fail-closed",
        )
    if trust not in AUTHORITY_TRUST:
        return ArchitectureDecision(
            decision_id=decision_id,
            accepted=False,
            citations=citations,
            freshness=freshness,
            trust=trust,
            reason="untrusted or unverified design evidence cannot authorize a change",
        )
    if change.get("compatibility_ok") is not True or change.get("source_aligned") is not True:
        return ArchitectureDecision(
            decision_id=decision_id,
            accepted=False,
            citations=citations,
            freshness=freshness,
            trust=trust,
            reason="compatibility or source alignment is not proven",
        )
    return ArchitectureDecision(
        decision_id=decision_id,
        accepted=True,
        citations=citations,
        freshness=freshness,
        trust=trust,
        reason="design change accepted against current authoritative citations; model output remains advisory",
    )


def evaluate_director_status(root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    portfolio = assign_local_portfolio(dict(body.get("resources") or {}))
    context = bound_local_context(
        list(body.get("context_items") or []),
        max_chars=int(body.get("max_chars") or 4000),
        max_items=int(body.get("max_items") or 8),
        max_age_seconds=int(body.get("max_age_seconds") or 3600),
    )
    recommendation = recommend_progress(dict(body.get("control") or {}))
    architecture = evaluate_architecture_change(dict(body.get("architecture") or {}))
    return {
        "portfolio": portfolio.model_dump(mode="json"),
        "context": context.model_dump(mode="json"),
        "recommendation": recommendation.model_dump(mode="json"),
        "architecture": architecture.model_dump(mode="json"),
        "root": str(root.resolve()),
        "user_action_required": False,
        "model_output_authoritative": False,
    }


def run_director_action(
    root: Path,
    action: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    body = payload or {}
    store = DirectorStore.open(root)
    try:
        if action == "status":
            return evaluate_director_status(root, body)
        if action == "portfolio":
            portfolio = assign_local_portfolio(body)
            store.put(
                "portfolio",
                _digest("portfolio", _canonical(body)),
                portfolio.model_dump(mode="json"),
            )
            return portfolio.model_dump(mode="json")
        if action == "bound-context":
            bounded = bound_local_context(
                list(body.get("items") or []),
                max_chars=int(body.get("max_chars") or 4000),
                max_items=int(body.get("max_items") or 8),
                max_age_seconds=int(body.get("max_age_seconds") or 3600),
            )
            return bounded.model_dump(mode="json")
        if action == "recommend":
            recommendation = recommend_progress(body)
            store.put(
                "recommendation",
                recommendation.recommendation_id,
                recommendation.model_dump(mode="json"),
            )
            return recommendation.model_dump(mode="json")
        if action == "architecture":
            architecture = evaluate_architecture_change(body)
            store.put(
                "architecture",
                architecture.decision_id,
                architecture.model_dump(mode="json"),
            )
            return architecture.model_dump(mode="json")
        if action == "decisions":
            return {
                "recommendations": store.list_kind("recommendation"),
                "architecture": store.list_kind("architecture"),
                "user_action_required": False,
            }
        raise ValueError(f"unsupported director-intelligence action: {action}")
    finally:
        store.close()
