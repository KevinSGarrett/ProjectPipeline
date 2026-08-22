from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_pipeline.domain.resilience import (
    FailureDomain,
    MachineHealth,
    MachineRole,
    RuntimeKind,
)
from project_pipeline.resilience.backup import BackupPlanner, load_recovery_objectives
from project_pipeline.resilience.failover import RecoveryDirector, decide_operating_mode
from project_pipeline.resilience.local_models import LocalModelGateway, load_local_runtimes

_SCENARIOS = (
    "provider-loss",
    "control-machine-loss",
    "split-brain",
    "aws-outage",
    "backup-restore",
    "gpu-unavailable",
)


def supported_scenarios() -> tuple[str, ...]:
    return _SCENARIOS


def _machine(machine_id: str, role: MachineRole, healthy: bool, token: int) -> MachineHealth:
    return MachineHealth(
        machine_id=machine_id,
        roles=(role,),
        healthy=healthy,
        heartbeat_at_utc=datetime.now(UTC) - timedelta(seconds=30),
        capabilities=("control",),
        capacity={"cpu": 1.0},
        fencing_token=token,
    )


def simulate_scenario(root: Path, scenario: str) -> dict[str, object]:
    if scenario not in _SCENARIOS:
        raise ValueError(f"unknown resilience scenario: {scenario}")
    director = RecoveryDirector()
    if scenario == "provider-loss":
        result = director.provider_substitution(
            ("reasoning",),
            (
                {"provider_id": "cloud-a", "available": False, "capabilities": ["reasoning"]},
                {
                    "provider_id": "local",
                    "available": True,
                    "capabilities": ["reasoning"],
                    "cost_score": 0.0,
                },
            ),
        )
        passed = result["selected_provider_id"] == "local" and result["task_semantics_preserved"]
        details = result
    elif scenario == "control-machine-loss":
        failover_decision = director.decide_failover(
            _machine("control-a", MachineRole.PRIMARY_CONTROL, False, 7),
            _machine("control-b", MachineRole.STANDBY_CONTROL, True, 7),
            witness_confirmed=True,
            active_lease_expired=True,
        )
        passed = (
            failover_decision.eligible
            and failover_decision.required_fencing_token == 8
            and failover_decision.reconcile_before_commit
        )
        details = failover_decision.model_dump(mode="json")
    elif scenario == "split-brain":
        failover_decision = director.decide_failover(
            _machine("control-a", MachineRole.PRIMARY_CONTROL, False, 7),
            _machine("control-b", MachineRole.STANDBY_CONTROL, True, 7),
            witness_confirmed=False,
            active_lease_expired=False,
        )
        passed = not failover_decision.eligible and failover_decision.witness_required
        details = failover_decision.model_dump(mode="json")
    elif scenario == "aws-outage":
        mode_decision = decide_operating_mode(
            (FailureDomain.CLOUD, FailureDomain.NETWORK), canonical_state_available=True
        )
        passed = (
            mode_decision.mode.value == "LOCAL_FIRST"
            and "deterministic_control" in mode_decision.allowed_capabilities
        )
        details = mode_decision.model_dump(mode="json")
    elif scenario == "backup-restore":
        planner = BackupPlanner(load_recovery_objectives(root))
        isolated = (
            Path(tempfile.gettempdir()) / "project-pipeline-restore-sim" / "isolated-postgres"
        )
        plan = planner.plan_restore(
            domain="canonical_state",
            repository="repo",
            isolated_target=str(isolated),
        )
        passed = (
            bool(plan["verification_required"])
            and bool(plan["backup_status_is_not_restore_status"])
            and not bool(plan["live_execution_performed"])
        )
        details = plan
    else:
        gateway = LocalModelGateway(load_local_runtimes(root))
        runtime = gateway.select(
            ("summarization",),
            available_kinds=(RuntimeKind.LLAMA_CPP, RuntimeKind.OLLAMA, RuntimeKind.LLAMA_SWAP),
        )
        mode_decision = decide_operating_mode((FailureDomain.GPU,), canonical_state_available=True)
        passed = (
            runtime is not None
            and mode_decision.mode.value == "DEGRADED"
            and "deterministic_control" in mode_decision.allowed_capabilities
        )
        details = {
            "selected_runtime": runtime.model_dump(mode="json") if runtime else None,
            "mode": mode_decision.model_dump(mode="json"),
        }
    return {
        "scenario": scenario,
        "passed": bool(passed),
        "details": details,
        "deterministic_authority_preserved": True,
        "external_mutation_performed": False,
    }
