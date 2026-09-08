"""Isolated published-byte journeys that do not mutate historical campaigns."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from project_pipeline.command_center.api import CommandCenterAuth, create_command_center_app
from project_pipeline.command_center.autonomy_director import PersistentAutonomyDirector
from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.models import HealthDimension, HealthState
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.persistence.migrations import SQLiteMigrationRunner
from project_pipeline.resilience.restore import RestoreIntentStore, RestoreTargetPolicy


def run_sqlite_migration_journey(root: Path, database: Path) -> dict[str, Any]:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        runner = SQLiteMigrationRunner(connection, root)
        applied = runner.apply_all()
        rolled = runner.rollback_last()
        reapplied = runner.apply_all()
    finally:
        connection.close()
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    return {
        "ok": bool(applied.applied) and bool(reapplied.applied),
        "journey": "sqlite_migration",
        "database_sha256_raw": digest,
        "applied": list(applied.applied),
        "rolled_back_pending": list(rolled.pending),
        "reapplied": list(reapplied.applied),
        "hash_algorithm": "sha256_raw",
    }


def run_persistent_director_journey(state_path: Path) -> dict[str, Any]:
    director = PersistentAutonomyDirector(state_path)
    projection = director.projection()
    return {
        "ok": projection.get("kind") == "persistent_autonomy_director"
        and projection.get("chat_mutation") is False,
        "journey": "persistent_director",
        "projection_keys": sorted(projection.keys()),
        "recovered": bool(projection.get("recovered")),
    }


def run_command_center_api_journey() -> dict[str, Any]:
    snapshot = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:published-byte",
        project_id="PROJECT-PIPELINE",
        operating_mode="NORMAL",
        health=(HealthDimension(name="control", state=HealthState.HEALTHY, reason="ok"),),
        completion_gate_state="NOT_COMPLETE",
    )
    app = create_command_center_app(
        snapshot_provider=lambda: snapshot,
        event_broker=RealtimeEventBroker(),
        inbox=AttentionNotificationBroker(),
        auth=CommandCenterAuth(lambda token: "actor:journey" if token == "good" else None),
    )
    client = TestClient(app)
    health = client.get("/healthz")
    status = client.get(
        "/api/v1/command-center/status", headers={"Authorization": "Bearer good"}
    )
    denied = client.get("/api/v1/command-center/status")
    return {
        "ok": health.status_code == 200
        and status.status_code == 200
        and denied.status_code == 401
        and status.json().get("completion_gate_state") == "NOT_COMPLETE",
        "journey": "command_center_api",
        "health_status": health.status_code,
        "authorized_status": status.status_code,
        "unauthorized_status": denied.status_code,
    }


def run_isolated_backup_restore_journey(workspace: Path) -> dict[str, Any]:
    source = workspace / "backup-source"
    target = workspace / "restore-target"
    source.mkdir(parents=True)
    (source / "artifact.txt").write_text("isolated-restore\n", encoding="utf-8")
    store = RestoreIntentStore(workspace / "restore.sqlite3")
    try:
        digest = hashlib.sha256(b"isolated-restore\n").hexdigest()
        policy = RestoreTargetPolicy([workspace])
        intent = store.record_intent(
            idempotency_key="c18-isolated-restore",
            domain="isolated_backup",
            target=target,
            manifest_sha256=digest,
        )
        store.dry_run(intent["intent_id"], policy)
        applied = store.apply(intent["intent_id"], source=source, policy=policy, approve=True)
        restored = (target / "artifact.txt").read_text(encoding="utf-8")
        return {
            "ok": applied["state"] == "APPLIED" and restored == "isolated-restore\n",
            "journey": "isolated_backup_restore",
            "intent_id": intent["intent_id"],
            "cloned_authority_database": False,
        }
    finally:
        store.close()
        if source.exists():
            shutil.rmtree(source, ignore_errors=True)
