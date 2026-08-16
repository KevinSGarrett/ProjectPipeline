from __future__ import annotations

import time
from pathlib import Path

from project_pipeline.assurance import build_repository_gate_facts, evaluate_completion_gate
from project_pipeline.budget.simulation import simulate_scenario as simulate_budget
from project_pipeline.domain.assurance import GateState
from project_pipeline.domain.verification import (
    GoldenJourneyDefinition,
    GoldenJourneyResult,
    VerificationResultState,
    verification_identifier,
)
from project_pipeline.orchestration.simulation import simulate_scenario as simulate_orchestration
from project_pipeline.upstream import validate_upstream_reviews


def definitions() -> tuple[GoldenJourneyDefinition, ...]:
    raw = (
        {
            "name": "Budget hard-stop preserves local control",
            "objective": "Paid work is stopped at the hard budget boundary while eligible local control work remains admissible.",
            "requirement_ids": ("REQ-BUDGET-0008", "REQ-BUDGET-0013", "REQ-CTRL-0015"),
            "environment": "Local deterministic Budget Governor simulation with no provider billing mutation.",
            "setup_steps": (
                "Load the repository Budget policy and deterministic hard-stop scenario.",
            ),
            "action_steps": ("Execute the hard_stop_local_continues budget simulation.",),
            "expected_results": (
                "Budget pressure reaches HARD_STOP.",
                "Eligible local control work remains admitted.",
            ),
            "cleanup_steps": (
                "Discard in-memory simulation state; no external resources were created.",
            ),
            "evidence_expectations": (
                "Structured pressure mode and admission notes are preserved in the golden-journey result.",
            ),
            "required_observations": ("hard-stop pressure reached", "local work admitted"),
            "risk": "HIGH",
        },
        {
            "name": "Durable unknown outcome requires reconciliation",
            "objective": "A lost external acknowledgement produces recovery-required state rather than a blind duplicate operation.",
            "requirement_ids": ("REQ-CTRL-0012", "REQ-ORCH-0014"),
            "environment": "Local PPDB-backed orchestration simulation with a deterministic lost-acknowledgement fault.",
            "setup_steps": (
                "Initialize the orchestration simulation with an external operation that can lose its acknowledgement.",
            ),
            "action_steps": ("Execute the unknown-outcome orchestration scenario.",),
            "expected_results": (
                "The workflow enters RECOVERY_REQUIRED.",
                "Blind external retry is not performed.",
            ),
            "cleanup_steps": (
                "Close simulation persistence and retain only the structured recovery observations.",
            ),
            "evidence_expectations": (
                "Recovery-required final state and unknown-outcome observations are preserved.",
            ),
            "required_observations": ("unknown outcome persisted", "blind retry avoided"),
            "risk": "CRITICAL",
        },
        {
            "name": "Completion Gate refuses premature completion",
            "objective": "The deterministic Completion Gate remains NOT_COMPLETE while later accepted project obligations are unfinished.",
            "requirement_ids": ("REQ-ASSURE-0004", "REQ-ASSURE-0016", "REQ-CTRL-0009"),
            "environment": "Current repository control state projected through the deterministic Execution Assurance Completion Gate.",
            "setup_steps": (
                "Build current repository gate facts from source-controlled plans, requirements, Jira, evidence, and architecture state.",
            ),
            "action_steps": (
                "Evaluate all required Completion Gate questions against current facts.",
            ),
            "expected_results": (
                "The gate returns NOT_COMPLETE while later obligations remain unfinished.",
                "No self-certification path can force final_complete true.",
            ),
            "cleanup_steps": (
                "No mutable state is created; preserve the structured gate observation only.",
            ),
            "evidence_expectations": (
                "Gate state and failed-question numbers are recorded in the journey result.",
            ),
            "required_observations": (
                "completion gate evaluated",
                "unfinished later obligations rejected",
            ),
            "risk": "CRITICAL",
        },
        {
            "name": "Upstream reuse continuation remains enforceable",
            "objective": "The permanent upstream-adoption validator remains clean after verification-harness activation work.",
            "requirement_ids": ("REQ-UPSTREAM-0001", "REQ-UPSTREAM-0002"),
            "environment": "Current source-controlled provenance and upstream-adoption registries; read-only validation only.",
            "setup_steps": (
                "Load the complete upstream catalog, terminal dispositions, usage registry, and activation gate.",
            ),
            "action_steps": ("Run upstream provenance/adoption validation.",),
            "expected_results": (
                "Upstream validation returns zero errors.",
                "Selection remains distinct from concrete integration.",
            ),
            "cleanup_steps": ("No cleanup required because the validator is read-only.",),
            "evidence_expectations": (
                "Upstream error count and selected-versus-integrated invariant observation are preserved.",
            ),
            "required_observations": (
                "upstream validator clean",
                "selected remains distinct from integrated",
            ),
            "risk": "HIGH",
        },
    )
    return tuple(
        GoldenJourneyDefinition(
            journey_id=verification_identifier("GJOURNEY", item["name"], item["objective"]),
            **item,
        )
        for item in raw
    )


def run_journey(root: Path, journey: GoldenJourneyDefinition) -> GoldenJourneyResult:
    started = time.perf_counter()
    observations: list[str] = []
    passed = False
    if journey.name == "Budget hard-stop preserves local control":
        result = simulate_budget(root, "hard_stop_local_continues")
        observations.extend(result.notes)
        observations.append(f"pressure:{result.pressure_mode.value}")
        passed = result.pressure_mode.value == "HARD_STOP" and any(
            note == "local_admitted:True" for note in result.notes
        )
    elif journey.name == "Durable unknown outcome requires reconciliation":
        result = simulate_orchestration(root, "unknown-outcome")
        observations.extend(result.observations)
        observations.append(f"final_state:{result.final_state}")
        passed = result.passed and result.final_state == "RECOVERY_REQUIRED"
    elif journey.name == "Completion Gate refuses premature completion":
        facts = build_repository_gate_facts(root, "PROJECT-PIPELINE")
        result = evaluate_completion_gate(facts)
        observations.append(f"state:{result.state.value}")
        observations.append(
            f"failed_questions:{','.join(str(item.question_number) for item in result.questions if not item.passed)}"
        )
        passed = result.state is GateState.NOT_COMPLETE and not result.final_complete
    elif journey.name == "Upstream reuse continuation remains enforceable":
        errors = validate_upstream_reviews(root)
        observations.append(f"upstream_errors:{len(errors)}")
        observations.append("selected_is_not_integrated invariant evaluated")
        passed = not errors
    else:
        raise ValueError(f"unsupported golden journey: {journey.name}")
    duration = int((time.perf_counter() - started) * 1000)
    return GoldenJourneyResult(
        result_id=verification_identifier(
            "GRESULT", journey.journey_id, str(passed), *observations
        ),
        journey_id=journey.journey_id,
        state=VerificationResultState.PASS if passed else VerificationResultState.FAIL,
        observations=tuple(observations),
        duration_ms=duration,
    )


def run_all(root: Path) -> tuple[GoldenJourneyResult, ...]:
    return tuple(run_journey(root, journey) for journey in definitions())
