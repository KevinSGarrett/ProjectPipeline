from __future__ import annotations

import sqlite3
from pathlib import Path

from project_pipeline.domain.agents import (
    AdapterQualificationReport,
    AgentRegistrySnapshot,
    CircuitBreakerRecord,
    ExecutionReceipt,
    PerformanceObservation,
    ProviderStateObservation,
    RoutingDecision,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class AgentRouterStore:
    def __init__(self, database: Path | str, root: Path) -> None:
        self.root = root.resolve()
        self.database = database
        self.db = sqlite3.connect(str(database))
        self.db.row_factory = sqlite3.Row

    def __enter__(self) -> AgentRouterStore:
        self.initialize()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def save_registry(self, item: AgentRegistrySnapshot) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO agent_registry_snapshots(registry_id,payload_json,created_at_utc) VALUES(?,?,?)",
                (item.registry_id, item.model_dump_json(), item.generated_at_utc.isoformat()),
            )

    def save_provider_state(self, item: ProviderStateObservation) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO agent_provider_states(provider_id,state,payload_json,observed_at_utc) VALUES(?,?,?,?)",
                (
                    item.provider_id,
                    item.state.value,
                    item.model_dump_json(),
                    item.observed_at_utc.isoformat(),
                ),
            )

    def provider_states(self) -> tuple[ProviderStateObservation, ...]:
        return tuple(
            ProviderStateObservation.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload_json FROM agent_provider_states ORDER BY provider_id"
            )
        )

    def save_circuit(self, item: CircuitBreakerRecord) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO agent_circuit_breakers(provider_id,circuit_state,payload_json,updated_at_utc) VALUES(?,?,?,?)",
                (
                    item.provider_id,
                    item.state.value,
                    item.model_dump_json(),
                    item.updated_at_utc.isoformat(),
                ),
            )

    def circuits(self) -> tuple[CircuitBreakerRecord, ...]:
        return tuple(
            CircuitBreakerRecord.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload_json FROM agent_circuit_breakers ORDER BY provider_id"
            )
        )

    def save_performance(self, item: PerformanceObservation) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO agent_performance_observations(observation_id,target_id,capability_id,success,payload_json,observed_at_utc) VALUES(?,?,?,?,?,?)",
                (
                    item.observation_id,
                    item.target_id,
                    item.capability_id,
                    int(item.success),
                    item.model_dump_json(),
                    item.observed_at_utc.isoformat(),
                ),
            )

    def performance(self) -> tuple[PerformanceObservation, ...]:
        return tuple(
            PerformanceObservation.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload_json FROM agent_performance_observations ORDER BY observed_at_utc,observation_id"
            )
        )

    def save_routing_decision(self, item: RoutingDecision) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO agent_routing_decisions(decision_id,task_id,selected_provider_id,payload_json,created_at_utc) VALUES(?,?,?,?,?)",
                (
                    item.decision_id,
                    item.task_id,
                    item.selected_provider_id,
                    item.model_dump_json(),
                    item.generated_at_utc.isoformat(),
                ),
            )

    def save_execution_receipt(self, item: ExecutionReceipt) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO agent_execution_receipts(receipt_id,task_id,succeeded,payload_json,created_at_utc) VALUES(?,?,?,?,?)",
                (
                    item.receipt_id,
                    item.task_id,
                    int(item.succeeded),
                    item.model_dump_json(),
                    item.generated_at_utc.isoformat(),
                ),
            )

    def routing_decisions(self) -> tuple[RoutingDecision, ...]:
        return tuple(
            RoutingDecision.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload_json FROM agent_routing_decisions ORDER BY created_at_utc,decision_id"
            )
        )

    def execution_receipts(self) -> tuple[ExecutionReceipt, ...]:
        return tuple(
            ExecutionReceipt.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload_json FROM agent_execution_receipts ORDER BY created_at_utc,receipt_id"
            )
        )

    def qualifications(self) -> tuple[AdapterQualificationReport, ...]:
        return tuple(
            AdapterQualificationReport.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload_json FROM agent_qualification_reports ORDER BY evaluated_at_utc,report_id"
            )
        )

    def save_qualification(self, item: AdapterQualificationReport) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO agent_qualification_reports(report_id,subject_id,subject_version,state,payload_json,evaluated_at_utc) VALUES(?,?,?,?,?,?)",
                (
                    item.report_id,
                    item.subject_id,
                    item.subject_version,
                    item.state.value,
                    item.model_dump_json(),
                    item.evaluated_at_utc.isoformat(),
                ),
            )

    def status(self) -> dict[str, str | int]:
        def c(t: str) -> int:
            return int(self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])

        return {
            "schema_version": "1.0.0",
            "registry_snapshots": c("agent_registry_snapshots"),
            "provider_states": c("agent_provider_states"),
            "circuit_breakers": c("agent_circuit_breakers"),
            "performance_observations": c("agent_performance_observations"),
            "routing_decisions": c("agent_routing_decisions"),
            "execution_receipts": c("agent_execution_receipts"),
            "qualification_reports": c("agent_qualification_reports"),
        }
