from datetime import UTC, datetime

from project_pipeline.agent_router import AgentRouterStore, build_registry
from project_pipeline.domain import (
    AgentSpec,
    CapabilitySpec,
    CircuitBreakerRecord,
    ExecutionMode,
    ModelSpec,
    PerformanceObservation,
    ProviderRuntimeState,
    ProviderSpec,
    ProviderStateObservation,
    QualificationState,
)
from project_pipeline.persistence import SQLiteMigrationRunner


def test_agent_router_store_roundtrip(tmp_path):
    root = __import__("pathlib").Path(__file__).parents[1]
    db = tmp_path / "state.db"
    now = datetime.now(UTC)
    cap = CapabilitySpec(capability_id="routine_reasoning", description="r")
    p = ProviderSpec(
        provider_id="provider:test",
        display_name="T",
        adapter_id="adapter:test",
        execution_mode=ExecutionMode.MOCK,
        capabilities=(cap.capability_id,),
    )
    m = ModelSpec(
        model_id="model:test",
        provider_id=p.provider_id,
        provider_model_name="m",
        version="1",
        capabilities=(cap.capability_id,),
        qualification=QualificationState.QUALIFIED,
    )
    a = AgentSpec(
        agent_id="agent:test",
        model_id=m.model_id,
        capabilities=(cap.capability_id,),
        qualification=QualificationState.QUALIFIED,
    )
    reg = build_registry(capabilities=(cap,), providers=(p,), models=(m,), agents=(a,), when=now)
    with AgentRouterStore(db, root) as store:
        store.save_registry(reg)
        store.save_provider_state(
            ProviderStateObservation(
                provider_id=p.provider_id, state=ProviderRuntimeState.HEALTHY, observed_at_utc=now
            )
        )
        store.save_circuit(CircuitBreakerRecord(provider_id=p.provider_id, updated_at_utc=now))
        store.save_performance(
            PerformanceObservation(
                observation_id="PERF-1234567890ABCDEFGHIJ",
                target_id=a.agent_id,
                capability_id=cap.capability_id,
                task_class="x",
                success=True,
                latency_ms=10,
                observed_at_utc=now,
            )
        )
        status = store.status()
        assert (
            status["registry_snapshots"] == 1
            and status["provider_states"] == 1
            and status["performance_observations"] == 1
        )
        assert store.performance()[0].observation_id.startswith("PERF-")
        assert store.circuits()[0].provider_id == p.provider_id
        assert store.provider_states()[0].provider_id == p.provider_id


def test_ppdb_0008_is_reversible(tmp_path):
    import sqlite3

    root = __import__("pathlib").Path(__file__).parents[1]
    db = sqlite3.connect(":memory:")
    runner = SQLiteMigrationRunner(db, root)
    runner.apply_all(target="PPDB-0008")
    assert runner.status().latest_applied == "PPDB-0008"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0007"
