from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from project_pipeline.domain.assurance import (
    CompletionGateDecision,
    IndependentReview,
    LoopGuardDecision,
    ScopeChangeDecision,
    ScopeContract,
    TruthRecord,
    VerificationPlan,
)

T = TypeVar("T", bound=BaseModel)


class AssuranceStore:
    def __init__(self, database: Path) -> None:
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _dump(value: BaseModel) -> str:
        return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def _put(self, table: str, key_name: str, key: str, project_id: str, value: BaseModel) -> None:
        payload = self._dump(value)
        with self._connect() as conn:
            existing = conn.execute(
                f"SELECT payload_json FROM {table} WHERE {key_name}=?", (key,)
            ).fetchone()
            if existing and existing["payload_json"] != payload:
                raise ValueError(f"immutable assurance record collision: {key}")
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({key_name}, project_id, payload_json) VALUES (?, ?, ?)",
                (key, project_id, payload),
            )

    def save_plan(self, value: VerificationPlan) -> None:
        self._put("assurance_verification_plans", "plan_id", value.plan_id, value.project_id, value)

    def save_truth(self, project_id: str, value: TruthRecord) -> None:
        self._put("assurance_truth_records", "truth_id", value.truth_id, project_id, value)

    def save_review(self, project_id: str, value: IndependentReview) -> None:
        self._put("assurance_reviews", "review_id", value.review_id, project_id, value)

    def save_loop(self, project_id: str, value: LoopGuardDecision) -> None:
        self._put("assurance_loop_decisions", "decision_id", value.decision_id, project_id, value)

    def save_scope(self, project_id: str, value: ScopeContract) -> None:
        self._put("assurance_scope_contracts", "scope_id", value.scope_id, project_id, value)

    def save_scope_change(self, project_id: str, value: ScopeChangeDecision) -> None:
        self._put("assurance_scope_changes", "change_id", value.change_id, project_id, value)

    def save_gate(self, value: CompletionGateDecision) -> None:
        self._put("assurance_gate_evaluations", "gate_id", value.gate_id, value.project_id, value)

    def status(self, project_id: str) -> dict[str, int]:
        tables = {
            "verification_plans": "assurance_verification_plans",
            "truth_records": "assurance_truth_records",
            "reviews": "assurance_reviews",
            "loop_decisions": "assurance_loop_decisions",
            "scope_contracts": "assurance_scope_contracts",
            "scope_changes": "assurance_scope_changes",
            "gate_evaluations": "assurance_gate_evaluations",
        }
        out = {}
        with self._connect() as conn:
            for name, table in tables.items():
                row = conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE project_id=?", (project_id,)
                ).fetchone()
                out[name] = int(row["n"])
        return out
