from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any

from project_pipeline.domain.scheduler import (
    LeaseBundle,
    ResourceClaim,
    ResourceLease,
    ResourcePool,
    ResourceRegistrySnapshot,
    SchedulerPlan,
    SchedulerSimulationResult,
    lease_expiry,
    local_resource_pools,
    scheduler_identifier,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class SchedulerStore:
    """Durable scheduler projections, resource pools, and fenced lease lifecycle."""

    def __init__(self, database: Path | str, root: Path) -> None:
        self.database = database
        self.root = root.resolve()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> SchedulerStore:
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
            raise RuntimeError("scheduler store is not open")
        return self.connection

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def register_pools(self, pools: Iterable[ResourcePool]) -> None:
        with self.db:
            for pool in pools:
                self.db.execute(
                    """
                    INSERT INTO scheduler_resource_pools
                        (resource_key, resource_type, capacity_units, reserved_units, machine_id,
                         observed, payload_json, updated_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(resource_key) DO UPDATE SET
                        resource_type=excluded.resource_type,
                        capacity_units=excluded.capacity_units,
                        reserved_units=excluded.reserved_units,
                        machine_id=excluded.machine_id,
                        observed=excluded.observed,
                        payload_json=excluded.payload_json,
                        updated_at_utc=excluded.updated_at_utc
                    """,
                    (
                        pool.resource_key,
                        pool.resource_type.value,
                        pool.capacity_units,
                        pool.reserved_units,
                        pool.machine_id,
                        int(pool.observed),
                        pool.model_dump_json(),
                        datetime.now(UTC).isoformat(),
                    ),
                )

    def ensure_local_pools(self) -> tuple[ResourcePool, ...]:
        pools = local_resource_pools(self.root)
        self.register_pools(pools)
        return pools

    def list_pools(self) -> tuple[ResourcePool, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM scheduler_resource_pools ORDER BY resource_key"
        ).fetchall()
        return tuple(ResourcePool.model_validate_json(row[0]) for row in rows)

    def _active_lease_rows(self, when: datetime) -> list[sqlite3.Row]:
        when_iso = when.astimezone(UTC).isoformat()
        return list(
            self.db.execute(
                """
                SELECT payload_json FROM scheduler_resource_leases
                WHERE released_at_utc IS NULL AND expires_at_utc > ?
                ORDER BY resource_key, fencing_token, lease_id
                """,
                (when_iso,),
            ).fetchall()
        )

    def list_active_leases(self, when: datetime | None = None) -> tuple[ResourceLease, ...]:
        when = (when or datetime.now(UTC)).astimezone(UTC)
        return tuple(
            ResourceLease.model_validate_json(row[0]) for row in self._active_lease_rows(when)
        )

    def recover_claims_for_task(
        self, task_id: str, *, holder_id: str | None = None
    ) -> tuple[ResourceClaim, ...]:
        rows = self.db.execute(
            """
            SELECT payload_json FROM scheduler_resource_leases
            WHERE task_id = ?
            ORDER BY acquired_at_utc DESC
            """,
            (task_id,),
        ).fetchall()
        if not rows:
            return ()
        leases = tuple(ResourceLease.model_validate_json(row[0]) for row in rows)
        if holder_id:
            same_holder = tuple(item for item in leases if item.holder_id == holder_id)
            if same_holder:
                leases = same_holder
        claims: list[ResourceClaim] = []
        seen: set[tuple[str, str, str, int]] = set()
        for lease in leases:
            key = (
                lease.claim.resource_type.value,
                lease.claim.resource_key,
                lease.claim.access_mode.value,
                lease.claim.quantity,
            )
            if key in seen:
                continue
            seen.add(key)
            claims.append(lease.claim)
        return tuple(claims)

    def registry_snapshot(self, when: datetime | None = None) -> ResourceRegistrySnapshot:
        when = (when or datetime.now(UTC)).astimezone(UTC)
        pools = self.list_pools()
        if not pools:
            pools = self.ensure_local_pools()
        return ResourceRegistrySnapshot.create(
            pools=pools,
            active_leases=self.list_active_leases(when),
            observed_at_utc=when,
        )

    def _next_fencing_token(self, resource_key: str) -> int:
        row = self.db.execute(
            "SELECT current_token FROM scheduler_fencing_tokens WHERE resource_key=?",
            (resource_key,),
        ).fetchone()
        token = 1 if row is None else int(row[0]) + 1
        self.db.execute(
            """
            INSERT INTO scheduler_fencing_tokens(resource_key, current_token)
            VALUES (?, ?)
            ON CONFLICT(resource_key) DO UPDATE SET current_token=excluded.current_token
            """,
            (resource_key, token),
        )
        return token

    def acquire_bundle(
        self,
        *,
        task_id: str,
        holder_id: str,
        claims: Iterable[ResourceClaim],
        ttl_seconds: int = 900,
        now: datetime | None = None,
    ) -> LeaseBundle:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        claims = tuple(claims)
        if not claims:
            return LeaseBundle(
                task_id=task_id,
                holder_id=holder_id,
                leases=(),
                acquired=False,
                reasons=("no_resource_claims",),
            )
        try:
            self.db.execute("BEGIN IMMEDIATE")
            pools = {item.resource_key: item for item in self.list_pools()}
            active = [
                ResourceLease.model_validate_json(row[0]) for row in self._active_lease_rows(now)
            ]
            created: list[ResourceLease] = []
            reasons: list[str] = []
            for claim in claims:
                # Idempotent reacquisition returns the existing same-task/holder/claim lease.
                existing_same = next(
                    (
                        lease
                        for lease in active
                        if lease.task_id == task_id
                        and lease.holder_id == holder_id
                        and lease.claim == claim
                    ),
                    None,
                )
                if existing_same is not None:
                    created.append(existing_same)
                    continue
                pool = pools.get(claim.resource_key)
                if pool is not None:
                    used = sum(
                        lease.claim.quantity
                        for lease in active + created
                        if lease.claim.resource_key == claim.resource_key
                    )
                    if used + claim.quantity > pool.allocatable_units:
                        reasons.append(
                            f"capacity:{claim.resource_key}:{claim.quantity}>{max(0, pool.allocatable_units - used)}"
                        )
                        break
                else:
                    conflict = next(
                        (lease for lease in active + created if claim.conflicts_with(lease.claim)),
                        None,
                    )
                    if conflict is not None:
                        reasons.append(f"lease:{claim.resource_key}:held_by:{conflict.holder_id}")
                        break
                token = self._next_fencing_token(claim.resource_key)
                lease = ResourceLease(
                    lease_id=scheduler_identifier(
                        "LEASE", task_id, holder_id, claim.resource_key, str(token)
                    ),
                    task_id=task_id,
                    holder_id=holder_id,
                    claim=claim,
                    fencing_token=token,
                    acquired_at_utc=now,
                    expires_at_utc=lease_expiry(now, ttl_seconds),
                )
                self.db.execute(
                    """
                    INSERT INTO scheduler_resource_leases
                        (lease_id, task_id, holder_id, resource_key, access_mode, quantity,
                         fencing_token, acquired_at_utc, expires_at_utc, released_at_utc, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        lease.lease_id,
                        lease.task_id,
                        lease.holder_id,
                        lease.claim.resource_key,
                        lease.claim.access_mode.value,
                        lease.claim.quantity,
                        lease.fencing_token,
                        lease.acquired_at_utc.isoformat(),
                        lease.expires_at_utc.isoformat(),
                        lease.model_dump_json(),
                    ),
                )
                created.append(lease)
            if reasons:
                self.db.rollback()
                return LeaseBundle(
                    task_id=task_id,
                    holder_id=holder_id,
                    leases=(),
                    acquired=False,
                    reasons=tuple(reasons),
                )
            self.db.commit()
            return LeaseBundle(
                task_id=task_id, holder_id=holder_id, leases=tuple(created), acquired=True
            )
        except Exception:
            self.db.rollback()
            raise

    def renew_lease(
        self,
        lease_id: str,
        *,
        holder_id: str,
        fencing_token: int,
        ttl_seconds: int = 900,
        now: datetime | None = None,
    ) -> ResourceLease:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        row = self.db.execute(
            "SELECT payload_json FROM scheduler_resource_leases WHERE lease_id=?", (lease_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown lease: {lease_id}")
        lease = ResourceLease.model_validate_json(row[0])
        if lease.released_at_utc is not None or lease.expires_at_utc <= now:
            raise ValueError("expired or released lease cannot be renewed")
        if lease.holder_id != holder_id or lease.fencing_token != fencing_token:
            raise ValueError("lease renewal rejected by holder/fencing-token check")
        renewed = lease.model_copy(
            update={
                "renewed_at_utc": now,
                "expires_at_utc": now + timedelta(seconds=ttl_seconds),
            }
        )
        with self.db:
            self.db.execute(
                "UPDATE scheduler_resource_leases SET expires_at_utc=?, payload_json=? WHERE lease_id=?",
                (renewed.expires_at_utc.isoformat(), renewed.model_dump_json(), lease_id),
            )
        return renewed

    def release_lease(
        self,
        lease_id: str,
        *,
        holder_id: str,
        fencing_token: int,
        now: datetime | None = None,
    ) -> ResourceLease:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        row = self.db.execute(
            "SELECT payload_json FROM scheduler_resource_leases WHERE lease_id=?", (lease_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown lease: {lease_id}")
        lease = ResourceLease.model_validate_json(row[0])
        if lease.holder_id != holder_id or lease.fencing_token != fencing_token:
            raise ValueError("lease release rejected by holder/fencing-token check")
        if lease.released_at_utc is not None:
            return lease
        released = lease.model_copy(update={"released_at_utc": now})
        with self.db:
            self.db.execute(
                "UPDATE scheduler_resource_leases SET released_at_utc=?, payload_json=? WHERE lease_id=?",
                (now.isoformat(), released.model_dump_json(), lease_id),
            )
        return released

    def save_plan(self, plan: SchedulerPlan) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO scheduler_plans
                    (plan_id, project_id, control_snapshot_id, registry_id, backpressure_mode,
                     lane_count, candidate_count, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    plan.project_id,
                    plan.control_snapshot_id,
                    plan.registry_id,
                    plan.backpressure.mode.value,
                    len(plan.lanes),
                    plan.candidate_count,
                    plan.model_dump_json(),
                    plan.generated_at_utc.isoformat(),
                ),
            )

    def latest_plan(self, project_id: str) -> SchedulerPlan | None:
        row = self.db.execute(
            """
            SELECT payload_json FROM scheduler_plans
            WHERE project_id=? ORDER BY created_at_utc DESC, plan_id DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return None if row is None else SchedulerPlan.model_validate_json(row[0])

    def save_simulation(self, result: SchedulerSimulationResult) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO scheduler_simulations
                    (simulation_id, scenario_name, plan_id, assertions_passed, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.simulation_id,
                    result.scenario_name,
                    result.plan.plan_id,
                    int(result.assertions_passed),
                    result.model_dump_json(),
                    result.plan.generated_at_utc.isoformat(),
                ),
            )

    def status(self, project_id: str) -> dict[str, Any]:
        plan_count = self.db.execute(
            "SELECT COUNT(*) FROM scheduler_plans WHERE project_id=?", (project_id,)
        ).fetchone()[0]
        active = self.list_active_leases()
        latest = self.latest_plan(project_id)
        return {
            "schema_version": "1.0.0",
            "project_id": project_id,
            "plan_count": int(plan_count),
            "latest_plan_id": latest.plan_id if latest else None,
            "latest_lane_count": len(latest.lanes) if latest else 0,
            "backpressure_mode": latest.backpressure.mode.value if latest else None,
            "resource_pool_count": len(self.list_pools()),
            "active_lease_count": len(active),
        }
