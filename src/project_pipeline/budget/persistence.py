from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType

from project_pipeline.budget.policy import build_snapshot
from project_pipeline.domain.budget import (
    BudgetAdmissionDecision,
    BudgetAdmissionRequest,
    BudgetAnomaly,
    BudgetForecast,
    BudgetLedgerEntry,
    BudgetLimit,
    BudgetPolicy,
    BudgetSnapshot,
    CostHistoryObservation,
    LedgerDirection,
    QuotaLimit,
    SpendLease,
    SpendLeaseState,
    budget_identifier,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class BudgetStore:
    """Transactional budget ledger, spend reservations, quotas, forecasts, and history."""

    def __init__(self, database: Path | str, root: Path) -> None:
        self.database = database
        self.root = root.resolve()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> BudgetStore:
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("budget store is not open")
        return self.connection

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def put_limit(self, limit: BudgetLimit, *, now: datetime | None = None) -> None:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        with self.db:
            self.db.execute(
                """
                INSERT INTO budget_limits
                    (limit_id, scope_key, cycle_id, hard_cap_microunits,
                     protected_reserve_microunits, payload_json, updated_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_key, cycle_id) DO UPDATE SET
                    limit_id=excluded.limit_id,
                    hard_cap_microunits=excluded.hard_cap_microunits,
                    protected_reserve_microunits=excluded.protected_reserve_microunits,
                    payload_json=excluded.payload_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (
                    limit.limit_id,
                    limit.scope_key,
                    limit.cycle_id,
                    limit.hard_cap_microunits,
                    limit.protected_reserve_microunits,
                    limit.model_dump_json(),
                    now.isoformat(),
                ),
            )

    def list_limits(self, cycle_id: str | None = None) -> tuple[BudgetLimit, ...]:
        if cycle_id is None:
            rows = self.db.execute(
                "SELECT payload_json FROM budget_limits ORDER BY scope_key, cycle_id"
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT payload_json FROM budget_limits WHERE cycle_id=? ORDER BY scope_key",
                (cycle_id,),
            ).fetchall()
        return tuple(BudgetLimit.model_validate_json(row[0]) for row in rows)

    def put_quota_limit(self, limit: QuotaLimit, *, now: datetime | None = None) -> None:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        with self.db:
            self.db.execute(
                """
                INSERT INTO budget_quota_limits
                    (quota_id, scope_key, provider_id, quota_name, capacity_units, payload_json, updated_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_key, provider_id, quota_name) DO UPDATE SET
                    quota_id=excluded.quota_id,
                    capacity_units=excluded.capacity_units,
                    payload_json=excluded.payload_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (
                    limit.quota_id,
                    limit.scope_key,
                    limit.provider_id,
                    limit.quota_name,
                    limit.capacity_units,
                    limit.model_dump_json(),
                    now.isoformat(),
                ),
            )

    def list_quota_limits(self) -> tuple[QuotaLimit, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM budget_quota_limits ORDER BY quota_id"
        ).fetchall()
        return tuple(QuotaLimit.model_validate_json(row[0]) for row in rows)

    def _insert_ledger(self, entry: BudgetLedgerEntry) -> BudgetLedgerEntry:
        row = self.db.execute(
            "SELECT payload_json FROM budget_ledger WHERE entry_id=?", (entry.entry_id,)
        ).fetchone()
        if row is not None:
            existing = BudgetLedgerEntry.model_validate_json(row[0])
            if existing != entry:
                raise ValueError(f"budget ledger idempotency collision: {entry.entry_id}")
            return existing
        self.db.execute(
            """
            INSERT INTO budget_ledger
                (entry_id, idempotency_key, project_id, task_id, provider_id, cost_class,
                 direction, cash_microunits, shadow_cost_microunits, payload_json,
                 observed_at_utc, recorded_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.entry_id,
                entry.idempotency_key,
                entry.project_id,
                entry.task_id,
                entry.provider_id,
                entry.cost_class.value,
                entry.direction.value,
                entry.cash_microunits,
                entry.shadow_cost_microunits,
                entry.model_dump_json(),
                entry.observed_at_utc.isoformat(),
                entry.recorded_at_utc.isoformat(),
            ),
        )
        return entry

    def record_ledger(self, entry: BudgetLedgerEntry) -> BudgetLedgerEntry:
        with self.db:
            return self._insert_ledger(entry)

    def list_ledger(
        self, *, project_id: str | None = None, task_id: str | None = None
    ) -> tuple[BudgetLedgerEntry, ...]:
        clauses: list[str] = []
        values: list[str] = []
        if project_id:
            clauses.append("project_id=?")
            values.append(project_id)
        if task_id:
            clauses.append("task_id=?")
            values.append(task_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.db.execute(
            f"SELECT payload_json FROM budget_ledger{where} ORDER BY observed_at_utc, entry_id",
            values,
        ).fetchall()
        return tuple(BudgetLedgerEntry.model_validate_json(row[0]) for row in rows)

    def _all_leases(self) -> tuple[SpendLease, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM budget_spend_leases ORDER BY created_at_utc, lease_id"
        ).fetchall()
        return tuple(SpendLease.model_validate_json(row[0]) for row in rows)

    def list_active_leases(
        self, *, now: datetime | None = None, project_id: str | None = None
    ) -> tuple[SpendLease, ...]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        active: list[SpendLease] = []
        for lease in self._all_leases():
            if project_id and lease.project_id != project_id:
                continue
            if lease.state is SpendLeaseState.UNKNOWN_OUTCOME or (
                lease.state is SpendLeaseState.RESERVED and lease.expires_at_utc > now
            ):
                active.append(lease)
        return tuple(active)

    def get_lease(self, lease_id: str) -> SpendLease | None:
        row = self.db.execute(
            "SELECT payload_json FROM budget_spend_leases WHERE lease_id=?", (lease_id,)
        ).fetchone()
        return None if row is None else SpendLease.model_validate_json(row[0])

    def _cash_totals(self, scope_key: str) -> tuple[int, int]:
        debits = 0
        credits = 0
        for entry in self.list_ledger():
            if scope_key not in entry.scope_keys:
                continue
            if entry.direction is LedgerDirection.DEBIT:
                debits += entry.cash_microunits
            else:
                credits += entry.cash_microunits
        return debits, credits

    def _committed(self, scope_key: str, now: datetime) -> int:
        return sum(
            lease.reserved_microunits
            for lease in self.list_active_leases(now=now)
            if scope_key in lease.scope_keys
        )

    def quota_used_or_reserved(self, quota_id: str, *, now: datetime | None = None) -> int:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        used = sum(entry.quota_units.get(quota_id, 0) for entry in self.list_ledger())
        reserved = sum(
            lease.quota_reservations.get(quota_id, 0) for lease in self.list_active_leases(now=now)
        )
        return used + reserved

    def snapshot(
        self,
        limit: BudgetLimit,
        *,
        policy: BudgetPolicy | None = None,
        forecast_p90_microunits: int = 0,
        pace_ratio_milli: int = 1000,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        policy = policy or BudgetPolicy()
        now = (now or datetime.now(UTC)).astimezone(UTC)
        debits, credits = self._cash_totals(limit.scope_key)
        committed = self._committed(limit.scope_key, now)
        return build_snapshot(
            scope_key=limit.scope_key,
            hard_cap_microunits=limit.hard_cap_microunits,
            protected_reserve_microunits=limit.protected_reserve_microunits,
            soft_cap_microunits=limit.soft_cap_microunits,
            spent_microunits=debits,
            credited_microunits=credits,
            committed_microunits=committed,
            forecast_p90_microunits=forecast_p90_microunits,
            pace_ratio_milli=pace_ratio_milli,
            policy=policy,
            observed_at_utc=now,
        )

    def snapshots_for_request(
        self,
        request: BudgetAdmissionRequest,
        *,
        cycle_id: str,
        policy: BudgetPolicy | None = None,
        forecast_p90_microunits: int = 0,
        pace_ratio_milli: int = 1000,
        now: datetime | None = None,
    ) -> tuple[BudgetSnapshot, ...]:
        wanted = set(request.scope_keys)
        limits = [
            item for item in self.list_limits(cycle_id) if item.enabled and item.scope_key in wanted
        ]
        return tuple(
            self.snapshot(
                item,
                policy=policy,
                forecast_p90_microunits=forecast_p90_microunits,
                pace_ratio_milli=pace_ratio_milli,
                now=now,
            )
            for item in limits
        )

    def save_decision(self, decision: BudgetAdmissionDecision) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO budget_admission_decisions
                    (decision_id, task_id, admitted, pressure_mode, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.task_id,
                    int(decision.admitted),
                    decision.pressure_mode.value,
                    decision.model_dump_json(),
                    decision.generated_at_utc.isoformat(),
                ),
            )

    def reserve(
        self,
        request: BudgetAdmissionRequest,
        decision: BudgetAdmissionDecision,
        *,
        cycle_id: str,
        idempotency_key: str,
        policy: BudgetPolicy | None = None,
        now: datetime | None = None,
    ) -> SpendLease:
        if not decision.admitted:
            raise ValueError("cannot reserve spend for a denied budget decision")
        policy = policy or BudgetPolicy()
        now = (now or datetime.now(UTC)).astimezone(UTC)
        lease_id = budget_identifier("LEASE", idempotency_key)
        requested_reservation = request.estimated_p90_microunits if request.paid_incremental else 0
        if requested_reservation > decision.authorized_microunits:
            raise ValueError("decision does not authorize the requested reservation")
        expires = now + timedelta(seconds=policy.lease_ttl_seconds)
        candidate = SpendLease(
            lease_id=lease_id,
            idempotency_key=idempotency_key,
            project_id=request.project_id,
            task_id=request.task_id,
            provider_id=request.provider_id,
            scope_keys=request.scope_keys,
            maximum_microunits=decision.authorized_microunits,
            reserved_microunits=requested_reservation,
            quota_reservations=request.quota_requirements,
            reserve_reason=request.reserve_reason if decision.reserve_authorized else None,
            reservation_evidence=(decision.decision_id,),
            created_at_utc=now,
            expires_at_utc=expires,
            updated_at_utc=now,
        )
        try:
            self.db.execute("BEGIN IMMEDIATE")
            existing_row = self.db.execute(
                "SELECT payload_json FROM budget_spend_leases WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing_row is not None:
                existing = SpendLease.model_validate_json(existing_row[0])
                if existing.project_id != request.project_id or existing.task_id != request.task_id:
                    raise ValueError("budget lease idempotency collision")
                self.db.rollback()
                return existing

            limits = [
                item
                for item in self.list_limits(cycle_id)
                if item.enabled and item.scope_key in set(request.scope_keys)
            ]
            if request.paid_incremental and not limits:
                raise ValueError("no applicable budget limit is configured")
            active = self.list_active_leases(now=now)
            ledger = self.list_ledger()
            for limit in limits:
                debit = sum(
                    item.cash_microunits
                    for item in ledger
                    if limit.scope_key in item.scope_keys
                    and item.direction is LedgerDirection.DEBIT
                )
                credit = sum(
                    item.cash_microunits
                    for item in ledger
                    if limit.scope_key in item.scope_keys
                    and item.direction is LedgerDirection.CREDIT
                )
                committed = sum(
                    item.reserved_microunits
                    for item in active
                    if limit.scope_key in item.scope_keys
                )
                cap = (
                    limit.hard_cap_microunits
                    if decision.reserve_authorized
                    else limit.normal_cap_microunits
                )
                if max(0, debit - credit) + committed + requested_reservation > cap:
                    raise ValueError(f"atomic budget reservation would exceed {limit.scope_key}")

            quota_limits = {
                item.quota_id: item for item in self.list_quota_limits() if item.enabled
            }
            for quota_id, units in request.quota_requirements.items():
                quota_limit = quota_limits.get(quota_id)
                if quota_limit is None:
                    raise ValueError(f"quota limit unavailable: {quota_id}")
                used = sum(item.quota_units.get(quota_id, 0) for item in ledger)
                reserved = sum(item.quota_reservations.get(quota_id, 0) for item in active)
                protected = 0 if decision.reserve_authorized else quota_limit.protected_units
                if used + reserved + units > quota_limit.capacity_units - protected:
                    raise ValueError(f"atomic quota reservation would exceed {quota_id}")

            self.db.execute(
                """
                INSERT INTO budget_spend_leases
                    (lease_id, idempotency_key, project_id, task_id, provider_id, state,
                     reserved_microunits, consumed_microunits, expires_at_utc, payload_json,
                     created_at_utc, updated_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.lease_id,
                    candidate.idempotency_key,
                    candidate.project_id,
                    candidate.task_id,
                    candidate.provider_id,
                    candidate.state.value,
                    candidate.reserved_microunits,
                    candidate.consumed_microunits,
                    candidate.expires_at_utc.isoformat(),
                    candidate.model_dump_json(),
                    candidate.created_at_utc.isoformat(),
                    candidate.updated_at_utc.isoformat(),
                ),
            )
            self.db.commit()
            return candidate
        except Exception:
            self.db.rollback()
            raise

    def _update_lease(self, lease: SpendLease) -> None:
        self.db.execute(
            """
            UPDATE budget_spend_leases SET state=?, reserved_microunits=?, consumed_microunits=?,
                expires_at_utc=?, payload_json=?, updated_at_utc=? WHERE lease_id=?
            """,
            (
                lease.state.value,
                lease.reserved_microunits,
                lease.consumed_microunits,
                lease.expires_at_utc.isoformat(),
                lease.model_dump_json(),
                lease.updated_at_utc.isoformat(),
                lease.lease_id,
            ),
        )

    def mark_unknown_outcome(self, lease_id: str, *, now: datetime | None = None) -> SpendLease:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        lease = self.get_lease(lease_id)
        if lease is None:
            raise KeyError(f"unknown budget lease: {lease_id}")
        if lease.state is not SpendLeaseState.RESERVED:
            raise ValueError("only a reserved lease can become unknown outcome")
        updated = lease.model_copy(
            update={
                "state": SpendLeaseState.UNKNOWN_OUTCOME,
                "reconciliation_required": True,
                "updated_at_utc": now,
            }
        )
        with self.db:
            self._update_lease(updated)
        return updated

    def resolve_unknown_no_effect(
        self, lease_id: str, *, now: datetime | None = None
    ) -> SpendLease:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        lease = self.get_lease(lease_id)
        if lease is None:
            raise KeyError(f"unknown budget lease: {lease_id}")
        if lease.state is not SpendLeaseState.UNKNOWN_OUTCOME:
            raise ValueError("lease is not awaiting unknown-outcome reconciliation")
        resolved = lease.model_copy(
            update={
                "state": SpendLeaseState.RELEASED,
                "reconciliation_required": False,
                "updated_at_utc": now,
            }
        )
        with self.db:
            self._update_lease(resolved)
        return resolved

    def release_lease(
        self, lease_id: str, *, cancelled: bool = False, now: datetime | None = None
    ) -> SpendLease:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        lease = self.get_lease(lease_id)
        if lease is None:
            raise KeyError(f"unknown budget lease: {lease_id}")
        if lease.state is SpendLeaseState.UNKNOWN_OUTCOME:
            raise ValueError("unknown-outcome reservation cannot be released before reconciliation")
        if lease.state is not SpendLeaseState.RESERVED:
            return lease
        state = SpendLeaseState.CANCELLED if cancelled else SpendLeaseState.RELEASED
        updated = lease.model_copy(update={"state": state, "updated_at_utc": now})
        with self.db:
            self._update_lease(updated)
        return updated

    def settle_lease(
        self,
        lease_id: str,
        entry: BudgetLedgerEntry,
        *,
        now: datetime | None = None,
    ) -> SpendLease:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        lease = self.get_lease(lease_id)
        if lease is None:
            raise KeyError(f"unknown budget lease: {lease_id}")
        if lease.state not in {SpendLeaseState.RESERVED, SpendLeaseState.UNKNOWN_OUTCOME}:
            raise ValueError("lease is not settleable")
        if entry.project_id != lease.project_id or entry.task_id != lease.task_id:
            raise ValueError("settlement ledger entry does not match lease task/project")
        state = (
            SpendLeaseState.OVERSPENT
            if entry.cash_microunits > lease.maximum_microunits
            else SpendLeaseState.SETTLED
        )
        updated = lease.model_copy(
            update={
                "consumed_microunits": entry.cash_microunits,
                "state": state,
                "reconciliation_required": False,
                "updated_at_utc": now,
            }
        )
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self._insert_ledger(entry)
            self._update_lease(updated)
            self.db.commit()
            return updated
        except Exception:
            self.db.rollback()
            raise

    def expire_stale_leases(self, *, now: datetime | None = None) -> tuple[SpendLease, ...]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        expired: list[SpendLease] = []
        try:
            self.db.execute("BEGIN IMMEDIATE")
            for lease in self._all_leases():
                if lease.state is SpendLeaseState.RESERVED and lease.expires_at_utc <= now:
                    updated = lease.model_copy(
                        update={"state": SpendLeaseState.EXPIRED, "updated_at_utc": now}
                    )
                    self._update_lease(updated)
                    expired.append(updated)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return tuple(expired)

    def save_history(self, observation: CostHistoryObservation) -> None:
        with self.db:
            row = self.db.execute(
                "SELECT payload_json FROM budget_cost_history WHERE observation_id=?",
                (observation.observation_id,),
            ).fetchone()
            if row is not None:
                if CostHistoryObservation.model_validate_json(row[0]) != observation:
                    raise ValueError("budget history identity collision")
                return
            self.db.execute(
                """
                INSERT INTO budget_cost_history
                    (observation_id, project_id, task_id, task_class, provider_id, cash_microunits,
                     verified, payload_json, observed_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.project_id,
                    observation.task_id,
                    observation.task_class,
                    observation.provider_id,
                    observation.cash_microunits,
                    int(observation.verified),
                    observation.model_dump_json(),
                    observation.observed_at_utc.isoformat(),
                ),
            )

    def list_history(self, *, project_id: str | None = None) -> tuple[CostHistoryObservation, ...]:
        if project_id is None:
            rows = self.db.execute(
                "SELECT payload_json FROM budget_cost_history ORDER BY observed_at_utc"
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT payload_json FROM budget_cost_history WHERE project_id=? ORDER BY observed_at_utc",
                (project_id,),
            ).fetchall()
        return tuple(CostHistoryObservation.model_validate_json(row[0]) for row in rows)

    def save_anomaly(self, anomaly: BudgetAnomaly) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO budget_anomalies
                    (anomaly_id, project_id, task_id, provider_id, severity, block_new_paid_work,
                     payload_json, detected_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    anomaly.anomaly_id,
                    anomaly.project_id,
                    anomaly.task_id,
                    anomaly.provider_id,
                    anomaly.severity,
                    int(anomaly.block_new_paid_work),
                    anomaly.model_dump_json(),
                    anomaly.detected_at_utc.isoformat(),
                ),
            )

    def list_anomalies(self, project_id: str) -> tuple[BudgetAnomaly, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM budget_anomalies WHERE project_id=? ORDER BY detected_at_utc, anomaly_id",
            (project_id,),
        ).fetchall()
        return tuple(BudgetAnomaly.model_validate_json(row[0]) for row in rows)

    def save_forecast(self, forecast: BudgetForecast) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO budget_forecasts
                    (forecast_id, project_id, task_class, provider_id, p50_microunits, p90_microunits,
                     payload_json, generated_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast.forecast_id,
                    forecast.project_id,
                    forecast.task_class,
                    forecast.provider_id,
                    forecast.p50_microunits,
                    forecast.p90_microunits,
                    forecast.model_dump_json(),
                    forecast.generated_at_utc.isoformat(),
                ),
            )

    def latest_forecast(self, project_id: str) -> BudgetForecast | None:
        row = self.db.execute(
            "SELECT payload_json FROM budget_forecasts WHERE project_id=? ORDER BY generated_at_utc DESC, forecast_id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return None if row is None else BudgetForecast.model_validate_json(row[0])

    def status(self, project_id: str, *, cycle_id: str | None = None) -> dict[str, object]:
        limits = self.list_limits(cycle_id)
        leases = self.list_active_leases(project_id=project_id)
        ledger = self.list_ledger(project_id=project_id)
        latest = self.latest_forecast(project_id)
        return {
            "schema_version": "1.0.0",
            "project_id": project_id,
            "cycle_id": cycle_id,
            "limit_count": len(limits),
            "quota_limit_count": len(self.list_quota_limits()),
            "ledger_entry_count": len(ledger),
            "active_lease_count": len(leases),
            "unknown_outcome_lease_count": sum(
                item.state is SpendLeaseState.UNKNOWN_OUTCOME for item in leases
            ),
            "latest_forecast_id": latest.forecast_id if latest else None,
            "anomaly_count": len(self.list_anomalies(project_id)),
            "blocking_anomaly_count": sum(
                item.block_new_paid_work for item in self.list_anomalies(project_id)
            ),
        }
