from __future__ import annotations

from pathlib import Path

from project_pipeline.domain.verification import (
    VerificationResultState,
    verification_identifier,
)
from project_pipeline.verification.faults import run_fault_scenarios
from project_pipeline.verification.golden import run_all as run_golden_journeys
from project_pipeline.verification.property_checks import run_properties


def supported_scenarios() -> tuple[str, ...]:
    return ("golden", "property", "fault")


def simulate_scenario(root: Path, scenario: str) -> dict[str, object]:
    if scenario == "golden":
        golden_results = run_golden_journeys(root)
        passed = all(item.state is VerificationResultState.PASS for item in golden_results)
        payload: list[object] = [item.model_dump(mode="json") for item in golden_results]
    elif scenario == "property":
        property_results = run_properties(root, seed=16016, cases=25)
        passed = all(item.passed for item in property_results)
        payload = [item.model_dump(mode="json") for item in property_results]
    elif scenario == "fault":
        fault_results = run_fault_scenarios(root)
        passed = all(item.passed for item in fault_results)
        payload = [item.model_dump(mode="json") for item in fault_results]
    else:
        raise ValueError(f"unsupported verification scenario: {scenario}")
    return {
        "simulation_id": verification_identifier("VRUN", "simulation", scenario, str(passed)),
        "scenario": scenario,
        "passed": passed,
        "results": payload,
    }
