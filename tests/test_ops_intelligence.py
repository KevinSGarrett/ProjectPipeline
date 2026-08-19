from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.observability.ops_health import calculate_health
from project_pipeline.observability.ops_models import (
    CacheOutcome,
    FailureClass,
    HealthLayerObservation,
    LayerState,
    MemoryKind,
    WorkerResult,
    WorkerRunRecord,
    ops_identifier,
)
from project_pipeline.observability.ops_service import (
    build_code_index,
    classify_dependency_updates,
    distill_memory,
    load_ops_health_dimensions,
    record_cache_outcome,
    record_cost,
    record_layer,
    record_worker,
    run_ops_action,
)
from project_pipeline.observability.ops_store import OpsIntelligenceStore, OpsStoreError

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _layer(
    layer: str,
    state: LayerState = LayerState.HEALTHY,
    *,
    when: datetime = NOW,
    suffix: str = "a",
) -> dict[str, object]:
    return {
        "observation_id": ops_identifier("layer", layer, suffix, when.isoformat()),
        "layer": layer,
        "state": state.value,
        "reason": f"{layer} observed",
        "recorded_at_utc": when.isoformat(),
        "evidence_ids": [],
        "factors": [f"{layer}:ok"],
    }


def _healthy_store(tmp_path: Path) -> OpsIntelligenceStore:
    store = OpsIntelligenceStore(tmp_path / "ops.sqlite3")
    for layer in (
        "component",
        "project",
        "provider",
        "synchronization",
        "budget",
        "evidence",
    ):
        record_layer(store, _layer(layer))
    return store


def test_health_is_unknown_when_required_layers_are_missing(tmp_path: Path) -> None:
    store = OpsIntelligenceStore(tmp_path / "ops.sqlite3")
    calculation = calculate_health(store, as_of_utc=NOW)
    assert calculation.overall is LayerState.UNKNOWN
    assert all(item.missing for item in calculation.layers)
    store.close()


def test_stale_observation_fails_closed(tmp_path: Path) -> None:
    store = _healthy_store(tmp_path)
    calculation = calculate_health(
        store, as_of_utc=NOW + timedelta(hours=3), freshness_seconds=3600
    )
    assert calculation.overall is LayerState.UNKNOWN
    assert all(item.stale for item in calculation.layers)
    store.close()


def test_contradictory_layer_is_unhealthy(tmp_path: Path) -> None:
    store = _healthy_store(tmp_path)
    record_layer(store, _layer("provider", LayerState.HEALTHY, suffix="left"))
    record_layer(store, _layer("provider", LayerState.DEGRADED, suffix="right"))
    calculation = calculate_health(store, as_of_utc=NOW)
    provider = next(item for item in calculation.layers if item.layer == "provider")
    assert provider.contradictory is True
    assert provider.state is LayerState.UNHEALTHY
    store.close()


def test_failed_worker_and_quota_breach_are_unhealthy(tmp_path: Path) -> None:
    store = _healthy_store(tmp_path)
    record_worker(
        store,
        {
            "run_id": ops_identifier("worker", "fail"),
            "capability": "review",
            "provider": "local",
            "model_or_tool_version": "test-1",
            "context_identity": "ctx-1",
            "started_at_utc": NOW.isoformat(),
            "ended_at_utc": NOW.isoformat(),
            "duration_ms": 10,
            "cpu_ms": 4,
            "memory_bytes": 128,
            "usage": {"tokens": 1, "token": "super-secret"},
            "result": WorkerResult.FAILED.value,
            "failure_class": FailureClass.PROVIDER.value,
            "recorded_at_utc": NOW.isoformat(),
        },
    )
    record_cost(
        store,
        {
            "sample_id": ops_identifier("cost", "over"),
            "spend": 8,
            "quota": 10,
            "reserved_lease": 5,
            "forecast": 12,
            "local_resource_use": 1,
            "verified_outcome_cost": 2,
            "recorded_at_utc": NOW.isoformat(),
        },
    )
    stored = WorkerRunRecord.model_validate(
        json.loads(str(store.list_kind("worker")[0]["payload_json"]))
    )
    assert stored.usage["token"] == "<redacted>"
    calculation = calculate_health(store, as_of_utc=NOW)
    assert calculation.overall is LayerState.UNHEALTHY
    store.close()


def test_complete_fresh_layers_are_healthy(tmp_path: Path) -> None:
    store = _healthy_store(tmp_path)
    calculation = calculate_health(store, as_of_utc=NOW)
    assert calculation.overall is LayerState.HEALTHY
    assert calculation.user_action_required is False
    store.close()


def test_code_index_and_dependency_classification_are_local() -> None:
    entries = build_code_index(ROOT, limit=20)
    assert entries
    assert all(item.file_sha256 for item in entries)
    assert any(item.path.replace("\\", "/").startswith("src/") for item in entries)
    updates = classify_dependency_updates(ROOT)
    assert updates
    assert any(item.criticality == "runtime" for item in updates)
    assert all(item.required_verification for item in updates)


def test_cache_and_distilled_memory(tmp_path: Path) -> None:
    store = OpsIntelligenceStore(tmp_path / "ops.sqlite3")
    event = record_cache_outcome(
        store,
        cache_kind="package",
        artifact_digest="a" * 64,
        layer="wheel",
        outcome=CacheOutcome.HIT,
        recorded_at_utc=NOW,
    )
    assert event.outcome is CacheOutcome.HIT
    try:
        distill_memory(store, {"chat": "hello", "kind": MemoryKind.FACT.value})
    except ValueError as error:
        assert "conversation history" in str(error)
    else:
        raise AssertionError("conversation history must be rejected")
    memory = distill_memory(
        store,
        {
            "memory_id": ops_identifier("mem", "fact"),
            "kind": MemoryKind.FACT.value,
            "statement": "Hosted required checks bind the exact PR head",
            "citations": ["REQ-OPS-0015"],
            "verified": True,
            "recorded_at_utc": NOW.isoformat(),
        },
    )
    assert memory.verified is True
    store.close()


def test_conflicting_replay_and_journal_recovery(tmp_path: Path) -> None:
    database = tmp_path / "ops.sqlite3"
    store = OpsIntelligenceStore(database)
    first = HealthLayerObservation.model_validate(_layer("project"))
    store.put_layer(first)
    try:
        store.put_layer(
            HealthLayerObservation.model_validate(_layer("project", LayerState.DEGRADED))
        )
        raise AssertionError("conflicting identifier must fail")
    except Exception as error:
        assert isinstance(error, (OpsStoreError, ValueError))
    store._connection().execute("DELETE FROM ops_records")
    restored = store.replay_journal()
    assert restored >= 1
    assert store.list_kind("layer")
    store.close()


def test_retention_and_concurrent_writers(tmp_path: Path) -> None:
    store = OpsIntelligenceStore(tmp_path / "ops.sqlite3")
    old = NOW - timedelta(days=40)
    record_layer(store, _layer("project", when=old, suffix="old"))
    deleted = store.apply_retention(retention_days=30)
    assert deleted >= 1

    def _write(index: int) -> str:
        record = record_worker(
            store,
            {
                "run_id": ops_identifier("worker", str(index)),
                "capability": "index",
                "provider": "local",
                "model_or_tool_version": "1",
                "context_identity": f"ctx-{index}",
                "started_at_utc": NOW.isoformat(),
                "ended_at_utc": NOW.isoformat(),
                "duration_ms": 1,
                "cpu_ms": 1,
                "memory_bytes": 1,
                "usage": {"n": index},
                "result": WorkerResult.SUCCEEDED.value,
                "failure_class": FailureClass.NONE.value,
                "recorded_at_utc": NOW.isoformat(),
            },
        )
        return record.run_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(_write, range(8)))
    assert len(set(ids)) == 8
    store.close()


def test_missing_store_does_not_rewrite_command_center_health(tmp_path: Path) -> None:
    assert load_ops_health_dimensions(None) == ()
    assert load_ops_health_dimensions(tmp_path) == ()


def test_cli_health_and_index(tmp_path: Path, capsys: object) -> None:
    payload = tmp_path / "layer.json"
    payload.write_text(json.dumps(_layer("component")), encoding="utf-8")
    code = main(
        [
            "ops-intelligence",
            "record-layer",
            "--root",
            str(tmp_path),
            "--payload",
            str(payload),
        ]
    )
    assert code == 0
    code = main(["ops-intelligence", "health", "--root", str(tmp_path)])
    assert code == 0
    code = main(["ops-intelligence", "classify-deps", "--root", str(ROOT)])
    assert code == 0
    captured = capsys.readouterr()
    assert "update_count" in captured.out


def test_run_ops_action_status(tmp_path: Path) -> None:
    status = run_ops_action(tmp_path, "status")
    assert status["user_action_required"] is False
    assert status["health"]["overall"] == "UNKNOWN"
