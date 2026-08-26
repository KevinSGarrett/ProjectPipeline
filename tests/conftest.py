from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# These tests verify the maintainers' local control workspace.  They need
# private Jira projections, plans, evidence, manifests, or editor automation
# that are deliberately excluded from a distributable source checkout.
PRIVATE_CONTROL_TEST_PATHS = frozenset(
    {
        "tests/test_agent_router_validation.py",
        "tests/test_architecture_registry.py",
        "tests/test_assurance_cli.py",
        "tests/test_assurance_compiler.py",
        "tests/test_assurance_completion.py",
        "tests/test_assurance_validation.py",
        "tests/test_attestation_recovery.py",
        "tests/test_autonomous_governance.py",
        "tests/test_autonomy_director.py",
        "tests/test_command_center_application.py",
        "tests/test_command_center_live.py",
        "tests/test_context_validation.py",
        "tests/test_control_cli.py",
        "tests/test_control_cohort_invariants.py",
        "tests/test_control_kernel.py",
        "tests/test_control_persistence.py",
        "tests/test_control_validation.py",
        "tests/test_core_state_store.py",
        "tests/test_cursor_cli_qualification.py",
        "tests/test_cursor_shell_hook.py",
        "tests/test_cursor_takeover.py",
        "tests/test_cycle11_pp380_384_bound.py",
        "tests/test_decision_resolution.py",
        "tests/test_domain_models.py",
        "tests/test_evidence_reconciliation_convergence.py",
        "tests/test_jira_cli.py",
        "tests/test_jira_graph.py",
        "tests/test_jira_implementation_reconciliation.py",
        "tests/test_jira_operational_alignment.py",
        "tests/test_jira_rebuild.py",
        "tests/test_jira_steward_domain.py",
        "tests/test_jira_steward_mock_and_service.py",
        "tests/test_jira_steward_persistence.py",
        "tests/test_jira_steward_validation.py",
        "tests/test_jira_sync_guard.py",
        "tests/test_pass23_full_e2e.py",
        "tests/test_pass24_release_hardening.py",
        "tests/test_pass25_final_convergence.py",
        "tests/test_pdef_0011_nonduration.py",
        "tests/test_pp380_corrected_dispositions.py",
        "tests/test_product_outcome_contract.py",
        "tests/test_release_continuation_and_post_deploy.py",
        "tests/test_release_factory.py",
        "tests/test_repository_contract.py",
        "tests/test_requirement_query.py",
        "tests/test_requirement_reconciliation.py",
        "tests/test_requirement_registries.py",
        "tests/test_requirement_truth_ledger.py",
        "tests/test_requirements_detailed.py",
        "tests/test_requirement_views.py",
        "tests/test_scheduler_cli.py",
        "tests/test_scheduler_validation.py",
        "tests/test_security_persistence_cli.py",
        "tests/test_security_supply_chain.py",
        "tests/test_security_validation.py",
        "tests/test_source_references.py",
        "tests/test_source_sections.py",
        "tests/test_state_cli.py",
        "tests/test_traceability_store.py",
        "tests/test_traceability.py",
        "tests/test_verification_cli.py",
        "tests/test_verification_golden.py",
        "tests/test_verification_mutation.py",
        "tests/test_verification_simulation.py",
        "tests/test_verification_validation.py",
    }
)


def is_standalone_public_source_checkout(root: Path = ROOT) -> bool:
    return not (root / "plans" / "PLAN_CATALOG.json").is_file() and all(
        (root / marker).exists()
        for marker in ("README.md", "LICENSE", "pyproject.toml", "src/project_pipeline")
    )


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    """Do not collect private-control tests from a public source checkout."""
    del config
    if not is_standalone_public_source_checkout():
        return False
    try:
        relative = collection_path.relative_to(ROOT).as_posix()
    except ValueError:
        return False
    return relative in PRIVATE_CONTROL_TEST_PATHS


@pytest.fixture
def project_root() -> Path:
    return ROOT
