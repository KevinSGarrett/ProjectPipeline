from __future__ import annotations

from project_pipeline.assurance.completion import evaluate_completion_gate
from project_pipeline.assurance.loop_guard import evaluate_loop
from project_pipeline.domain.assurance import (
    AssuranceSimulationResult,
    AttemptBudget,
    AttemptObservation,
    CompletionGateFacts,
    LoopDisposition,
    assurance_fingerprint,
    assurance_identifier,
)


def supported_scenarios() -> tuple[str, ...]:
    return ("complete", "stale_or_missing_gate", "attempt_loop", "external_block_only")


def _facts(**overrides) -> CompletionGateFacts:
    base = dict(
        project_id="PROJECT-PIPELINE",
        source_requirements_dispositioned=True,
        accepted_requirements_complete_or_external=True,
        implementation_traceability_complete=True,
        critical_paths_tested=True,
        golden_journeys_pass=True,
        security_gates_satisfied=True,
        resilience_verified=True,
        deployment_reproducible=True,
        rollback_verified=True,
        engineer_operable_from_docs=True,
        ai_continuable_from_repo_and_jira=True,
        unresolved_items_truthful=True,
        command_center_truthful=True,
        jira_truthful=True,
        unattended_operating_loop_qualified=True,
        unexplained_gap_count=0,
        snapshot_fingerprint="a" * 64,
    )
    base.update(overrides)
    return CompletionGateFacts(**base)


def simulate_scenario(scenario: str) -> AssuranceSimulationResult:
    if scenario not in supported_scenarios():
        raise ValueError(f"unsupported assurance scenario: {scenario}")
    observations = []
    passed = True
    if scenario == "complete":
        gate = evaluate_completion_gate(_facts())
        passed = gate.final_complete
        observations.append(gate.state.value)
    elif scenario == "stale_or_missing_gate":
        gate = evaluate_completion_gate(_facts(golden_journeys_pass=False))
        passed = not gate.final_complete and any(
            f.category.value == "GOLDEN_JOURNEY" for f in gate.failures
        )
        observations.extend((gate.state.value, "golden journey blocks completion"))
    elif scenario == "external_block_only":
        gate = evaluate_completion_gate(
            _facts(deployment_reproducible=False, externally_blocked_question_numbers=(8,))
        )
        passed = gate.state.value == "BLOCKED_EXTERNAL"
        observations.append(gate.state.value)
    else:
        fp = "b" * 64
        attempts = tuple(
            AttemptObservation(
                task_id="PP-TASK-TEST",
                attempt_number=i,
                action_fingerprint=fp,
                tool_fingerprint=fp,
                output_fingerprint=fp,
                state_fingerprint=fp,
                failure_signature="same",
                progress_units=0,
            )
            for i in range(1, 4)
        )
        decision = evaluate_loop(
            attempts,
            AttemptBudget(
                task_id="PP-TASK-TEST",
                max_attempts=5,
                used_attempts=3,
                max_same_failure=2,
                max_unchanged_outputs=2,
            ),
        )
        passed = decision.disposition is LoopDisposition.STOP_AND_ESCALATE
        observations.append(decision.disposition.value)
    fingerprint = assurance_fingerprint((scenario, passed, observations))
    return AssuranceSimulationResult(
        simulation_id=assurance_identifier("SIM", scenario, fingerprint),
        scenario=scenario,
        passed=passed,
        observations=tuple(observations),
    )
