"""Persistent Autonomy Director above the Control Kernel.

Director Chat is not this component. Raw chat text cannot mutate director state
or select work. Canonical transitions remain with Project Control.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.domain.control import ControlSnapshot


class AutonomyDirectorError(RuntimeError):
    """Fail-closed persistent director error."""


def default_state_path(root: Path) -> Path:
    return root.resolve() / ".local" / "state" / "autonomy_director" / "director_state.json"


@dataclass(frozen=True, slots=True)
class DirectorDecision:
    decision_id: str
    selected_task_id: str | None
    citations: tuple[str, ...]
    rationale: str
    control_snapshot_id: str
    decided_at_utc: datetime


class PersistentAutonomyDirector:
    """Persist director decisions across process restart without chat mutation."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path.resolve()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {
                "schema_version": "1.0.0",
                "revision": 0,
                "decisions": [],
                "last_selected_task_id": None,
                "recovered": False,
            }
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise AutonomyDirectorError("director state is not an object")
        return payload

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.state_path)

    def reject_raw_chat_mutation(self, text: str) -> None:
        raise AutonomyDirectorError(
            "raw chat cannot mutate Persistent Autonomy Director state or select work"
        )

    def select_next_work(
        self,
        control: ControlSnapshot,
        *,
        now: datetime | None = None,
    ) -> DirectorDecision:
        now = now or datetime.now(UTC)
        ready = tuple(item.task_id for item in control.sequence.ordered_ready_work)
        selected = ready[0] if ready else None
        citations = (
            f"control:{control.snapshot_id}",
            f"fingerprint:{control.snapshot_fingerprint}",
            *(f"ready:{task_id}" for task_id in ready[:8]),
        )
        if selected is None:
            rationale = "Control Kernel reports no ready work; director does not invent a lane."
        else:
            rationale = (
                "Director selected the highest-ranked Control-ready lane without replacing "
                "canonical transition authority."
            )
        revision = int(self._state.get("revision") or 0) + 1
        decision = DirectorDecision(
            decision_id=f"DIRDEC-{revision:08d}",
            selected_task_id=selected,
            citations=citations,
            rationale=rationale,
            control_snapshot_id=control.snapshot_id,
            decided_at_utc=now,
        )
        decisions = list(self._state.get("decisions") or [])
        decisions.append(
            {
                "decision_id": decision.decision_id,
                "selected_task_id": decision.selected_task_id,
                "citations": list(decision.citations),
                "rationale": decision.rationale,
                "control_snapshot_id": decision.control_snapshot_id,
                "decided_at_utc": decision.decided_at_utc.isoformat(),
            }
        )
        self._state = {
            "schema_version": "1.0.0",
            "revision": revision,
            "decisions": decisions[-50:],
            "last_selected_task_id": selected,
            "recovered": False,
            "updated_at_utc": now.isoformat(),
        }
        self._save()
        return decision

    def recover(self) -> dict[str, Any]:
        self._state = self._load()
        self._state["recovered"] = True
        self._save()
        return {
            "revision": int(self._state.get("revision") or 0),
            "last_selected_task_id": self._state.get("last_selected_task_id"),
            "decision_count": len(self._state.get("decisions") or []),
            "recovered": True,
        }

    def projection(self) -> dict[str, Any]:
        return {
            "kind": "persistent_autonomy_director",
            "authoritative_for_transitions": False,
            "canonical_authority": "PROJECT_CONTROL_KERNEL",
            "revision": int(self._state.get("revision") or 0),
            "last_selected_task_id": self._state.get("last_selected_task_id"),
            "decision_count": len(self._state.get("decisions") or []),
            "recovered": bool(self._state.get("recovered")),
            "chat_mutation": False,
        }
