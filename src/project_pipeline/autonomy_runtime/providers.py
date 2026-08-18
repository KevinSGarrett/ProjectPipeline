from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.service import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    LocalSubprocessDispatchAdapter,
)

SECRET_SHAPED = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"
    r"|sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}"
)
SENSITIVE_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)$")
REDACTED = "<redacted>"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def contains_secret_shaped(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            SENSITIVE_KEY.search(str(key)) or contains_secret_shaped(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret_shaped(item) for item in value)
    if isinstance(value, str):
        return bool(SECRET_SHAPED.search(value))
    return False


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): REDACTED
            if contains_secret_shaped(key) or contains_secret_shaped(item)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and contains_secret_shaped(value):
        return REDACTED
    return value


@dataclass(frozen=True)
class ProviderQualification:
    provider_id: str
    label: str
    qualified: bool
    expires_at_utc: datetime | None
    attestation_id: str | None
    capabilities: tuple[str, ...]

    def is_live_eligible(self, now: datetime | None = None) -> bool:
        if self.label == "fake":
            return False
        if not self.qualified or not self.attestation_id:
            return False
        if self.expires_at_utc is None:
            return True
        return self.expires_at_utc > (now or _utc_now())


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reason: str
    decision_id: str


class AutonomyProviderRuntime:
    """Qualified local/provider dispatch with durable intent, fencing, and redacted receipts."""

    def __init__(self, state_path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or _utc_now
        self._db = sqlite3.connect(str(state_path))
        self._db.row_factory = sqlite3.Row
        self._adapter = LocalSubprocessDispatchAdapter()
        with self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS provider_intents (
                    intent_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    provider_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_unknown (
                    intent_id TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        self._db.close()

    def _now(self) -> datetime:
        return self._clock()

    def dispatch(
        self,
        *,
        provider: ProviderQualification,
        command: list[str],
        working_directory: Path,
        task_id: str,
        worker_id: str,
        model_or_tool: str,
        budget: BudgetDecision,
        lease_fence: str,
        expected_fence: str,
        idempotency_key: str,
        extra: dict[str, Any] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        payload = {
            "provider_id": provider.provider_id,
            "label": provider.label,
            "command": command,
            "task_id": task_id,
            "worker_id": worker_id,
            "model_or_tool": model_or_tool,
            "lease_fence": lease_fence,
            "extra": extra or {},
        }
        if contains_secret_shaped(payload):
            raise ValueError("secret-shaped provider input is denied")
        if not provider.is_live_eligible(self._now()) and provider.label != "fake":
            raise ValueError("provider qualification missing or expired")
        if provider.label == "fake" and extra and extra.get("claim_live"):
            raise ValueError("fake provider cannot satisfy live qualification")
        if not budget.allowed:
            raise ValueError(f"budget denied: {budget.reason}")
        if lease_fence != expected_fence:
            raise ValueError("stale fence")
        input_digest = _digest(payload)
        with self._db:
            existing = self._db.execute(
                "SELECT * FROM provider_intents WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                if str(existing["input_digest"]) != input_digest:
                    raise ValueError("idempotency key conflict")
                receipt = self._db.execute(
                    "SELECT * FROM provider_receipts WHERE intent_id = ?",
                    (str(existing["intent_id"]),),
                ).fetchone()
                if receipt is not None:
                    replayed = json.loads(str(receipt["payload_json"]))
                    if not isinstance(replayed, dict):
                        raise TypeError("provider receipt must be a JSON object")
                    return replayed
                unknown = self._db.execute(
                    "SELECT * FROM provider_unknown WHERE intent_id = ?",
                    (str(existing["intent_id"]),),
                ).fetchone()
                if unknown is not None:
                    raise ValueError("unknown provider outcome must be reconciled before retry")
                intent_id = str(existing["intent_id"])
            else:
                intent_id = f"PRV-{_digest({'key': idempotency_key})[:12]}"
                self._db.execute(
                    """
                    INSERT INTO provider_intents (
                        intent_id, idempotency_key, provider_id, payload_json,
                        input_digest, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        intent_id,
                        idempotency_key,
                        provider.provider_id,
                        json.dumps(payload, sort_keys=True),
                        input_digest,
                        _iso(self._now()),
                    ),
                )
        try:
            result = self._adapter.execute(
                command=command,
                working_directory=working_directory,
                timeout_seconds=timeout_seconds,
                max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
            )
        except Exception as error:
            with self._db:
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO provider_unknown (intent_id, reason, created_at_utc)
                    VALUES (?, ?, ?)
                    """,
                    (intent_id, str(error), _iso(self._now())),
                )
            raise ValueError(f"unknown provider outcome: {error}") from error
        receipt = {
            "intent_id": intent_id,
            "status": "SUCCEEDED"
            if result["exit_code"] == 0 and not result["timed_out"]
            else "FAILED",
            "provider_id": provider.provider_id,
            "label": provider.label,
            "live_qualification": provider.is_live_eligible(self._now()),
            "task_id": task_id,
            "worker_id": worker_id,
            "model_or_tool": model_or_tool,
            "input_digest": input_digest,
            "budget_decision_id": budget.decision_id,
            "lease_fence": lease_fence,
            "egress": "local-subprocess",
            "result": redact(result),
        }
        receipt["receipt_sha256"] = _digest(receipt)
        with self._db:
            self._db.execute(
                """
                INSERT OR IGNORE INTO provider_receipts (
                    receipt_id, intent_id, status, payload_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    receipt["receipt_sha256"],
                    intent_id,
                    receipt["status"],
                    json.dumps(receipt, sort_keys=True),
                    _iso(self._now()),
                ),
            )
            self._db.execute("DELETE FROM provider_unknown WHERE intent_id = ?", (intent_id,))
        return receipt

    def reconcile_unknown(self, intent_id: str, *, applied: bool) -> None:
        with self._db:
            if applied:
                self._db.execute("DELETE FROM provider_unknown WHERE intent_id = ?", (intent_id,))
            else:
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO provider_unknown (intent_id, reason, created_at_utc)
                    VALUES (?, ?, ?)
                    """,
                    (intent_id, "RECONCILED_UNAPPLIED", _iso(self._now())),
                )

    def receipt_for_intent(self, intent_id: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT payload_json FROM provider_receipts WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        return None if row is None else json.loads(str(row["payload_json"]))


def local_test_provider(provider_id: str = "provider:local-test") -> ProviderQualification:
    return ProviderQualification(
        provider_id=provider_id,
        label="local",
        qualified=True,
        expires_at_utc=_utc_now() + timedelta(hours=1),
        attestation_id="ATT-LOCAL-TEST",
        capabilities=("local-subprocess",),
    )


def fake_provider(provider_id: str = "provider:fake") -> ProviderQualification:
    return ProviderQualification(
        provider_id=provider_id,
        label="fake",
        qualified=True,
        expires_at_utc=_utc_now() + timedelta(hours=1),
        attestation_id="ATT-FAKE",
        capabilities=("simulated",),
    )
