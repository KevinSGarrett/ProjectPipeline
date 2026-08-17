from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from project_pipeline.domain.lifecycle import (
    ClosureReadiness,
    ContractEvolution,
    ContractPhase,
    CrossRepositoryChangeSet,
    DataClassification,
    EnvironmentLease,
    EnvironmentType,
    PlatformReleaseCandidate,
    PortfolioMode,
    ProjectPortfolioRegistration,
    ProjectTerminalState,
    QualificationState,
    RepositoryBinding,
    RepositoryRole,
    RetentionPolicy,
)
from project_pipeline.domain.lifecycle import (
    TestDataAsset as LifecycleTestDataAsset,
)
from project_pipeline.lifecycle import (
    ContractEvolutionManager,
    EnvironmentManager,
    InformationLifecycleManager,
    MultiRepositoryCoordinator,
    PlatformUpgradeGovernor,
    PortfolioGovernor,
    ProjectClosureDirector,
    TestDataLifecycleManager,
    VersionQualificationManager,
    assess_adoption_maturity,
    simulate_scenario,
    validate_lifecycle_foundation,
)
from project_pipeline.lifecycle.persistence import LifecycleStore


def project(
    pid: str, priority: int, guarantee: int = 1, cap: int = 100
) -> ProjectPortfolioRegistration:
    return ProjectPortfolioRegistration(
        project_id=pid,
        authority_id=f"AUTH-{pid}",
        priority=priority,
        guaranteed_worker_slots=guarantee,
        max_worker_share_percent=cap,
        budget_weight=1,
        operator_importance=50,
        credential_scope_id=f"CRED-{pid}",
        context_scope_id=f"CTX-{pid}",
        permission_scope_id=f"PERM-{pid}",
    )


def test_portfolio_preserves_minimum_capacity_and_caps():
    g = PortfolioGovernor((project("A", 90, 1, 60), project("B", 20, 1, 60)))
    rows = g.allocate(total_worker_slots=5)
    by = {x.project_id: x for x in rows}
    assert by["A"].worker_slots >= 1 and by["B"].worker_slots >= 1
    assert by["A"].worker_slots <= 3 and by["B"].worker_slots <= 3


def test_portfolio_deadline_sprint_requires_known_project():
    g = PortfolioGovernor((project("A", 50),))
    with pytest.raises(ValueError):
        g.allocate(total_worker_slots=2, mode=PortfolioMode.DEADLINE_SPRINT, favored_project_id="B")


def test_portfolio_rejects_duplicate_project_identity():
    with pytest.raises(ValueError):
        PortfolioGovernor((project("A", 1), project("A", 2)))


def test_multi_repo_change_set_enforces_dependencies():
    repos = (
        RepositoryBinding(
            repository_id="backend",
            canonical_url="https://example/backend",
            role=RepositoryRole.BACKEND,
            steward_id="S1",
            revision="a",
        ),
        RepositoryBinding(
            repository_id="frontend",
            canonical_url="https://example/front",
            role=RepositoryRole.FRONTEND,
            steward_id="S2",
            revision="b",
            dependencies=("backend",),
        ),
    )
    c = CrossRepositoryChangeSet(
        change_set_id="CHANGESET-1",
        project_id="P",
        requirement_ids=("REQ-1",),
        repository_changes={"backend": "PR-1", "frontend": "PR-2"},
        merge_order=("backend", "frontend"),
        shared_change_identity="CHG-1",
    )
    assert MultiRepositoryCoordinator(repos).validate_change_set(c)["merge_order_valid"]


def test_multi_repo_change_set_detects_bad_order():
    repos = (
        RepositoryBinding(
            repository_id="backend",
            canonical_url="https://example/backend",
            role=RepositoryRole.BACKEND,
            steward_id="S1",
            revision="a",
        ),
        RepositoryBinding(
            repository_id="frontend",
            canonical_url="https://example/front",
            role=RepositoryRole.FRONTEND,
            steward_id="S2",
            revision="b",
            dependencies=("backend",),
        ),
    )
    c = CrossRepositoryChangeSet(
        change_set_id="CHANGESET-2",
        project_id="P",
        requirement_ids=(),
        repository_changes={"backend": "PR-1", "frontend": "PR-2"},
        merge_order=("frontend", "backend"),
        shared_change_identity="CHG-2",
    )
    assert not MultiRepositoryCoordinator(repos).validate_change_set(c)["merge_order_valid"]


def test_temporary_environment_requires_ttl():
    lease = EnvironmentLease(
        environment_id="ENV-1",
        project_id="P",
        environment_type=EnvironmentType.TEMPORARY_TEST,
        owner_id="T",
        revision="a",
        namespace="n",
        data_classification=DataClassification.SYNTHETIC,
    )
    with pytest.raises(ValueError):
        EnvironmentManager().validate_lease(lease)


def test_production_derived_test_data_is_denied_without_permission_and_transformation():
    lease = EnvironmentLease(
        environment_id="ENV-2",
        project_id="P",
        environment_type=EnvironmentType.TEMPORARY_TEST,
        owner_id="T",
        revision="a",
        namespace="n",
        ttl_seconds=3600,
        data_classification=DataClassification.PRODUCTION_DERIVED,
    )
    with pytest.raises(PermissionError):
        EnvironmentManager().validate_lease(lease)


def test_preview_leak_detection_does_not_authorize_cleanup():
    now = datetime.now(UTC)
    lease = EnvironmentLease(
        environment_id="ENV-3",
        project_id="P",
        environment_type=EnvironmentType.PREVIEW,
        owner_id="PR",
        revision="a",
        namespace="n",
        created_at_utc=now - timedelta(hours=8),
        ttl_seconds=3600,
        data_classification=DataClassification.SYNTHETIC,
    )
    row = EnvironmentManager().leak_status(lease, now=now)
    assert (
        row["leaked"] and row["cleanup_plan_required"] and not row["destructive_cleanup_authorized"]
    )


def test_sensitive_test_data_requires_masking():
    asset = LifecycleTestDataAsset(
        asset_id="DATA-1",
        project_id="P",
        classification=DataClassification.SENSITIVE_TEST,
        provenance="snapshot",
        access_policy_id="POL",
        refresh_policy="manual",
        retention_days=7,
        destruction_mode="secure",
    )
    with pytest.raises(PermissionError):
        TestDataLifecycleManager().validate_asset(asset)


def evolution(phase: ContractPhase, incompatible=(), evidence=()) -> ContractEvolution:
    return ContractEvolution(
        evolution_id="EV-1",
        contract_id="API",
        from_version="1",
        to_version="2",
        phase=phase,
        compatible_consumers=("a",),
        incompatible_consumers=tuple(incompatible),
        migration_plan_id="MIG-1",
        rollback_plan_id="RB-1",
        verification_evidence_ids=tuple(evidence),
    )


def test_contract_evolution_is_one_phase_at_a_time():
    assert ContractEvolutionManager().can_advance(
        evolution(ContractPhase.EXPAND), ContractPhase.MIGRATE
    )["allowed"]
    assert not ContractEvolutionManager().can_advance(
        evolution(ContractPhase.EXPAND), ContractPhase.VERIFY
    )["allowed"]


def test_contract_cannot_verify_with_incompatible_consumer():
    assert not ContractEvolutionManager().can_advance(
        evolution(ContractPhase.MIGRATE, ("frontend",)), ContractPhase.VERIFY
    )["allowed"]


def test_contract_cannot_contract_without_evidence():
    assert not ContractEvolutionManager().can_advance(
        evolution(ContractPhase.VERIFY), ContractPhase.CONTRACT
    )["allowed"]
    assert ContractEvolutionManager().can_advance(
        evolution(ContractPhase.VERIFY, evidence=("EVID-1",)), ContractPhase.CONTRACT
    )["allowed"]


def test_reference_aware_gc_requires_expiry_and_zero_refs_and_never_authorizes_delete():
    p = RetentionPolicy(class_id="debug", retention_days=1)
    now = datetime.now(UTC)
    x = InformationLifecycleManager().gc_decision(
        policy=p, created_at_utc=now - timedelta(days=3), live_reference_count=0, now=now
    )
    assert x["eligible_for_gc_plan"] and not x["deletion_authorized"]
    y = InformationLifecycleManager().gc_decision(
        policy=p, created_at_utc=now - timedelta(days=3), live_reference_count=1, now=now
    )
    assert not y["eligible_for_gc_plan"]


def test_legal_hold_blocks_gc_plan():
    p = RetentionPolicy(class_id="audit", retention_days=1)
    x = InformationLifecycleManager().gc_decision(
        policy=p,
        created_at_utc=datetime.now(UTC) - timedelta(days=3),
        live_reference_count=0,
        legal_hold=True,
    )
    assert not x["eligible_for_gc_plan"]


def test_project_closure_requires_full_readiness():
    s = ClosureReadiness(
        project_id="P", current_state=ProjectTerminalState.CLOSING, final_requirements_verified=True
    )
    assert not ProjectClosureDirector().readiness(s)["can_archive"]


def test_project_archive_plan_is_non_destructive():
    s = ClosureReadiness(
        project_id="P",
        current_state=ProjectTerminalState.CLOSING,
        final_requirements_verified=True,
        final_release_signed=True,
        jira_reconciled=True,
        git_clean=True,
        evidence_archive_built=True,
        jira_snapshot_built=True,
        handoff_built=True,
        unused_resources_release_planned=True,
        credentials_revocation_planned=True,
        scheduled_tasks_disable_planned=True,
        final_backup_restore_verified=True,
    )
    p = ProjectClosureDirector().plan_archive(s)
    assert p["can_archive"] and p["target_state"] == "ARCHIVED" and not p["live_mutation_performed"]


def test_new_version_is_quarantined_from_high_risk_routing():
    q = VersionQualificationManager().observe_new_version(
        subject_kind="tool", subject_id="codex", version="2", compatibility_profile="default"
    )
    assert q.state == QualificationState.QUALIFICATION and not q.high_risk_routing_allowed


def test_version_promotion_requires_conformance_and_shadow_or_canary():
    m = VersionQualificationManager()
    q = m.observe_new_version(
        subject_kind="tool", subject_id="codex", version="2", compatibility_profile="default"
    )
    with pytest.raises(ValueError):
        m.promote(q, conformance_evidence_ids=("E1",), shadow_or_canary_evidence_ids=())
    assert (
        m.promote(q, conformance_evidence_ids=("E1",), shadow_or_canary_evidence_ids=("E2",)).state
        == QualificationState.ACTIVE
    )


def release(cert=(), canary=()) -> PlatformReleaseCandidate:
    return PlatformReleaseCandidate(
        release_id="REL-1",
        artifact_sha256="a" * 64,
        platform_version="2",
        schema_version="2",
        adapter_versions={"a": "1"},
        policy_version="1",
        profile_version="1",
        migration_plan_id="MIG",
        rollback_plan_id="RB",
        synthetic_e2e_certification_evidence_ids=tuple(cert),
        canary_or_shadow_evidence_ids=tuple(canary),
        post_upgrade_verification_plan_id="POST",
    )


def test_platform_release_requires_synthetic_e2e_and_canary_shadow():
    assert not PlatformUpgradeGovernor().eligibility(release())["eligible_to_control_real_projects"]
    assert PlatformUpgradeGovernor().eligibility(release(("E1",), ("E2",)))[
        "eligible_to_control_real_projects"
    ]


def test_adoption_maturity_is_read_only_and_measurable():
    a = assess_adoption_maturity(
        project_id="P",
        observed={
            "discovery_complete": True,
            "baseline_captured": True,
            "gap_analysis_complete": True,
            "adoption_plan_approved": True,
        },
    )
    assert a.score == 50 and not a.authoritative_assets_mutated_by_assessment


@pytest.mark.parametrize(
    "scenario",
    [
        "shared-destructive-test-target",
        "production-data-copy",
        "leaked-preview",
        "premature-closure",
        "retention-with-live-reference",
    ],
)
def test_lifecycle_fault_scenarios_preserve_authority(scenario):
    assert simulate_scenario(scenario)["deterministic_authority_preserved"]


def test_ppdb_0018_store_and_rollback(project_root, tmp_path):
    from project_pipeline.persistence.migrations import SQLiteMigrationRunner

    db = tmp_path / "life.db"
    with LifecycleStore(db, project_root) as s:
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0018" in ids
        s.save_json(
            "lifecycle_project_closures",
            "project_id",
            "P",
            {"state": "ACTIVE", "updated_at_utc": "2026-08-15T00:00:00Z"},
            {"project_id": "P"},
        )
        assert s.status()["lifecycle_project_closures"] == 1
        runner = SQLiteMigrationRunner(s.db, project_root)
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0020" not in ids and "PPDB-0019" in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0019" not in ids and "PPDB-0018" in ids
        runner.rollback_last()
        ids = {x[0] for x in s.db.execute("SELECT migration_id FROM schema_migrations")}
        assert "PPDB-0018" not in ids and "PPDB-0017" in ids


def test_pass22_lifecycle_validator(project_root):
    assert validate_lifecycle_foundation(project_root) == []
