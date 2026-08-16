from pathlib import Path

from project_pipeline.verification.property_checks import run_properties


def test_deterministic_property_probes_pass(project_root: Path):
    results = run_properties(project_root, seed=16016, cases=50)
    assert len(results) == 2
    assert all(item.passed for item in results)
    assert all(item.failure_count == 0 for item in results)


def test_property_probe_identity_is_reproducible(project_root: Path):
    first = run_properties(project_root, seed=7, cases=20)
    second = run_properties(project_root, seed=7, cases=20)
    assert [item.property_id for item in first] == [item.property_id for item in second]
