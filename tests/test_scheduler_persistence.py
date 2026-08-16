from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.domain.scheduler import AccessMode, ResourceClaim, ResourcePool, ResourceType
from project_pipeline.persistence import SQLiteMigrationRunner
from project_pipeline.scheduler.persistence import SchedulerStore

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 15, tzinfo=UTC)


def test_scheduler_migration_applies_and_rolls_back(tmp_path: Path) -> None:
    db = sqlite3.connect(tmp_path / "migrations.db")
    runner = SQLiteMigrationRunner(db, ROOT)
    status = runner.apply_all()
    assert "PPDB-0007" in status.applied
    while runner.status().latest_applied != "PPDB-0007":
        runner.rollback_last()
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0006"
    with pytest.raises(sqlite3.OperationalError):
        db.execute("SELECT COUNT(*) FROM scheduler_resource_pools").fetchone()
    db.close()


def test_atomic_lease_bundle_and_capacity(tmp_path: Path) -> None:
    path = tmp_path / "scheduler.db"
    with SchedulerStore(path, ROOT) as store:
        store.register_pools(
            (
                ResourcePool(
                    resource_key="machine:test/cpu",
                    resource_type=ResourceType.CPU_SLOT,
                    capacity_units=3,
                    reserved_units=1,
                ),
            )
        )
        claims = (
            ResourceClaim(
                resource_key="machine:test/cpu",
                resource_type=ResourceType.CPU_SLOT,
                access_mode=AccessMode.SHARED,
                quantity=2,
            ),
            ResourceClaim(resource_key="path:exclusive", resource_type=ResourceType.SERVICE),
        )
        first = store.acquire_bundle(
            task_id="PP-TASK-000001", holder_id="worker:1", claims=claims, ttl_seconds=60, now=NOW
        )
        assert first.acquired and len(first.leases) == 2
        second = store.acquire_bundle(
            task_id="PP-TASK-000002",
            holder_id="worker:2",
            claims=(
                ResourceClaim(
                    resource_key="machine:test/cpu",
                    resource_type=ResourceType.CPU_SLOT,
                    access_mode=AccessMode.SHARED,
                ),
            ),
            ttl_seconds=60,
            now=NOW,
        )
        assert not second.acquired
        assert any(reason.startswith("capacity:") for reason in second.reasons)


def test_lease_fencing_renew_release_and_expiry(tmp_path: Path) -> None:
    with SchedulerStore(tmp_path / "scheduler.db", ROOT) as store:
        claim = ResourceClaim(
            resource_key="environment:staging", resource_type=ResourceType.ENVIRONMENT
        )
        bundle = store.acquire_bundle(
            task_id="PP-TASK-000001", holder_id="worker:1", claims=(claim,), ttl_seconds=30, now=NOW
        )
        lease = bundle.leases[0]
        with pytest.raises(ValueError):
            store.renew_lease(
                lease.lease_id,
                holder_id="worker:1",
                fencing_token=lease.fencing_token + 1,
                ttl_seconds=30,
                now=NOW + timedelta(seconds=1),
            )
        renewed = store.renew_lease(
            lease.lease_id,
            holder_id="worker:1",
            fencing_token=lease.fencing_token,
            ttl_seconds=60,
            now=NOW + timedelta(seconds=1),
        )
        assert renewed.expires_at_utc > lease.expires_at_utc
        released = store.release_lease(
            lease.lease_id,
            holder_id="worker:1",
            fencing_token=lease.fencing_token,
            now=NOW + timedelta(seconds=2),
        )
        assert released.released_at_utc is not None
        next_bundle = store.acquire_bundle(
            task_id="PP-TASK-000002",
            holder_id="worker:2",
            claims=(claim,),
            ttl_seconds=30,
            now=NOW + timedelta(seconds=3),
        )
        assert next_bundle.acquired
        assert next_bundle.leases[0].fencing_token > lease.fencing_token
