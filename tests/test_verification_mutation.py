from pathlib import Path

from project_pipeline.verification.mutation import run_mutation_probes


def test_verification_mutation_probes_detect_all_mutations(project_root: Path):
    results = run_mutation_probes(project_root)
    assert len(results) == 3
    assert all(item.detected for item in results)
