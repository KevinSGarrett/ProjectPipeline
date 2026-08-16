from pathlib import Path

from project_pipeline.verification.faults import run_fault_scenarios


def test_fault_scenarios_cover_required_resilience_failure_classes(project_root: Path):
    values = run_fault_scenarios(project_root)
    assert {item.scenario for item in values} == {
        "provider-error",
        "provider-latency-timeout",
        "network-loss",
        "lost-backend-acknowledgement",
        "worker-termination",
        "quota-exhaustion",
        "dependency-failure",
    }
    assert all(item.passed for item in values)
