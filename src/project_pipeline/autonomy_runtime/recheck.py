"""Durable autonomous recheck of scoped external preconditions.

A blocked capability never globally pauses unrelated lanes. Rechecks are owned
by the autonomy runtime, persist outside chat, and never assign operator work.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.projection import (
    LIVE_EXTERNAL_PRECONDITION,
    live_text_is_forbidden,
    project_runtime_state,
)

DEFAULT_INTERVAL_SECONDS = 900
RUNTIME_OWNER = "autonomy-runtime"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse(value: str) -> datetime:
    return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))


class AutonomousRecheckStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": "1.0.0", "items": []}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("recheck store must be a JSON object")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError("recheck store items must be a list")
        return {"schema_version": "1.0.0", "items": list(items)}

    def save(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if live_text_is_forbidden(encoded):
            raise ValueError("recheck store cannot persist forbidden live phrases")
        self.path.write_text(encoded, encoding="utf-8", newline="\n")

    def schedule(
        self,
        *,
        capability: str,
        reason: str,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        now: datetime | None = None,
        affected_lane_ids: tuple[str, ...] = (),
        continuing_lane_ids: tuple[str, ...] = (),
        owner: str = RUNTIME_OWNER,
    ) -> dict[str, Any]:
        current = _aware(now or datetime.now(UTC))
        next_at = current + timedelta(seconds=interval_seconds)
        item = {
            "capability": capability,
            "reason": reason,
            "status": LIVE_EXTERNAL_PRECONDITION,
            "stored_status": project_runtime_state(LIVE_EXTERNAL_PRECONDITION),
            "owner": owner,
            "last_observed_at_utc": current.isoformat(),
            "next_recheck_at_utc": next_at.isoformat(),
            "interval_seconds": interval_seconds,
            "affected_lane_ids": list(affected_lane_ids),
            "continuing_lane_ids": list(continuing_lane_ids),
        }
        payload = self.load()
        remaining = [
            row
            for row in payload["items"]
            if isinstance(row, dict) and row.get("capability") != capability
        ]
        remaining.append(item)
        payload["items"] = remaining
        self.save(payload)
        return item

    def due(self, *, now: datetime | None = None) -> tuple[dict[str, Any], ...]:
        current = _aware(now or datetime.now(UTC))
        due_items: list[dict[str, Any]] = []
        for row in self.load()["items"]:
            if not isinstance(row, dict):
                continue
            next_at = _parse(str(row["next_recheck_at_utc"]))
            if next_at <= current:
                due_items.append(row)
        return tuple(due_items)

    def snapshot(self) -> dict[str, Any]:
        payload = self.load()
        return {
            "count": len(payload["items"]),
            "items": payload["items"],
            "global_stop": False,
            "owner": RUNTIME_OWNER,
        }
