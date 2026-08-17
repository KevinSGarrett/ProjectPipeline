from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline import __version__
from project_pipeline.agent_router import (
    AgentRouter,
    AgentRouterStore,
    load_agent_registry,
    simulate_provider_failover,
)
from project_pipeline.architecture import (
    find_components,
    load_technology_stack,
    summarize_architecture,
    write_architecture_views,
)
from project_pipeline.archive import create_archive, verify_archive
from project_pipeline.assurance import (
    AssurancePolicy,
    AssuranceStore,
    assess_candidate_completion,
    build_repository_gate_facts,
    compile_repository_plan,
    evaluate_completion_gate,
    evaluate_delivery_gate,
    evaluate_loop,
    evaluate_scope_change,
    load_delivery_policy,
)
from project_pipeline.assurance.simulation import (
    simulate_scenario as simulate_assurance_scenario,
)
from project_pipeline.assurance.simulation import (
    supported_scenarios as supported_assurance_scenarios,
)
from project_pipeline.budget import BudgetGovernor, BudgetStore, InfracostAdapter
from project_pipeline.budget.simulation import (
    simulate_scenario as simulate_budget_scenario,
)
from project_pipeline.budget.simulation import (
    supported_scenarios as supported_budget_scenarios,
)
from project_pipeline.configuration import (
    ConfigurationError,
    ExternalWriteMode,
    PersistenceBackend,
    SecretResolutionError,
    SecretResolver,
    load_runtime_configuration,
)
from project_pipeline.context_engine import ContextCompiler, ContextService, ContextStore
from project_pipeline.contracts import (
    ActionIntent,
    ApprovalState,
    RiskLevel,
    validate_schemas,
    write_schemas,
)
from project_pipeline.control import ControlGraphError, ControlStore, ProjectControlKernel
from project_pipeline.dependencies import (
    build_environment_lock,
    dependency_snapshot,
    dependency_status,
    validate_dependency_lock,
    write_dependency_snapshot,
)
from project_pipeline.domain import (
    BackpressureSignals,
    CircuitBreakerRecord,
    ExecutionTaskContract,
    IntakeMode,
    JiraAuthorityMode,
    JiraCommentIntent,
    JiraCommentKind,
    JiraIssueType,
    JiraLifecycleState,
    JiraReconciliationPlan,
    JiraRemoteSnapshot,
    OwnershipKind,
    ProjectIntakeRequest,
    ProjectLifecycleState,
    ProjectProfile,
    ProjectScale,
    ProviderRuntimeState,
    ProviderStateObservation,
    TaskLifecycleState,
    TraceabilityLinkType,
    TraceabilityMutation,
)
from project_pipeline.domain.assurance import AttemptBudget, AttemptObservation, ScopeContract
from project_pipeline.domain.budget import (
    BudgetAdmissionDecision,
    BudgetAdmissionRequest,
    BudgetLedgerEntry,
    BudgetLimit,
    BudgetPolicy,
    QuotaLimit,
)
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPolicy,
    DelegationEnvelope,
    ProviderEgress,
    ReceiptStatus,
)
from project_pipeline.domain.orchestration import (
    DurableBackendKind,
    WorkflowDefinition,
    WorkflowSignal,
    WorkflowStartRequest,
    orchestration_identifier,
)
from project_pipeline.domain.security import RootOfTrust, SecurityIdentity
from project_pipeline.github_steward import (
    GitHubRestAdapter,
    GitHubStewardError,
    GitHubStewardStore,
    LocalGitError,
    LocalGitRepository,
    MockGitHubAdapter,
    RepositorySteward,
)
from project_pipeline.intake import (
    BootstrapError,
    DiscoveryError,
    compile_project,
    detect_project_profile,
    discover_repository,
    discovery_summary,
    write_compilation_bundle,
)
from project_pipeline.jira import rebuild_jira_indexes
from project_pipeline.jira_steward import (
    AtlassianJiraCloudAdapter,
    JiraMirrorRepository,
    JiraSteward,
    JiraStewardError,
    MockJiraAdapter,
    export_jira_mirror,
    load_jira_export,
    load_jira_reconciliation_policy,
)
from project_pipeline.jira_steward.persistence import JiraSyncStore
from project_pipeline.jira_steward.sync_guard import evaluate_jira_sync_guard
from project_pipeline.lifecycle import (
    AttestationState,
    DurableAttestation,
    DurableProviderQualificationEvidence,
    LaneState,
    ProviderQualificationState,
    SessionIdentity,
    global_stop_required,
    provider_dispatch_blocked,
    scoped_lane_state,
    validate_durable_attestation,
    validate_provider_qualification_evidence,
)
from project_pipeline.line_numbering import generate_line_numbered_plans
from project_pipeline.manifest import write_manifest
from project_pipeline.orchestration import (
    DBOSFallbackAdapter,
    HatchetDurableAdapter,
    LocalDurableRuntime,
    MockDurableBackend,
    OrchestrationStore,
    RecoveryManager,
    TemporalFallbackAdapter,
)
from project_pipeline.orchestration.service import OrchestrationService
from project_pipeline.orchestration.simulation import (
    simulate_scenario as simulate_orchestration_scenario,
)
from project_pipeline.orchestration.simulation import (
    supported_scenarios,
)
from project_pipeline.persistence import PersistenceError, SQLiteStateStore
from project_pipeline.persistence.migrations import SQLiteMigrationRunner
from project_pipeline.quality import run_quality, write_quality_report
from project_pipeline.repository_map import write_repository_map
from project_pipeline.requirement_views import write_requirement_views
from project_pipeline.requirements import (
    find_requirements,
    requirement_index,
    summarize_requirements,
)
from project_pipeline.resilience import (
    BackupPlanner,
    LocalModelGateway,
    ResilienceStore,
    load_local_runtimes,
    load_recovery_objectives,
)
from project_pipeline.resilience import (
    simulate_scenario as simulate_resilience_scenario,
)
from project_pipeline.resilience import (
    supported_scenarios as supported_resilience_scenarios,
)
from project_pipeline.resilience.aws import aws_safety_plan
from project_pipeline.runtime import run_bootstrap, run_foundation_smoke
from project_pipeline.scheduler import (
    DynamicLaneScheduler,
    SchedulerStore,
    profiles_from_repository,
)
from project_pipeline.scheduler import (
    simulate_scenario as simulate_scheduler_scenario,
)
from project_pipeline.security import (
    SecurityStore,
    build_repository_sbom,
    evaluate_supply_chain,
)
from project_pipeline.security.simulation import simulate_security, supported_security_scenarios
from project_pipeline.security.supply_chain import assess_self_modification
from project_pipeline.services import (
    CoreStateService,
    ProjectIntakeService,
    RequirementTraceabilityService,
)
from project_pipeline.traceability import rebuild_traceability_exports, write_coverage_artifacts
from project_pipeline.upstream import (
    find_upstreams,
    load_p0_convergence,
    summarize_upstreams,
    write_upstream_views,
)
from project_pipeline.upstream_integrations.resilience import (
    activation_snapshot as resilience_activation_snapshot,
)
from project_pipeline.upstream_integrations.security import (
    AgeAdapter,
    ConftestAdapter,
    CosignVerifyAdapter,
    GitleaksAdapter,
    OpaAdapter,
    OsvScannerAdapter,
    ScorecardAdapter,
    SopsAdapter,
    TrivyAdapter,
    ZizmorAdapter,
)
from project_pipeline.validation import RepositoryValidator
from project_pipeline.verification import (
    VerificationHarness,
    VerificationStore,
    load_verification_policy,
)
from project_pipeline.verification import (
    activation_snapshot as verification_activation_snapshot,
)
from project_pipeline.verification import (
    default_check_specs as verification_default_check_specs,
)
from project_pipeline.verification import (
    find_chromium as verification_find_chromium,
)
from project_pipeline.verification import (
    golden_journey_definitions as verification_golden_journey_definitions,
)
from project_pipeline.verification import (
    render_verification_report as verification_render_report,
)
from project_pipeline.verification import (
    run_golden_journeys as verification_run_golden_journeys,
)
from project_pipeline.verification import (
    simulate_scenario as simulate_verification_scenario,
)
from project_pipeline.verification import (
    supported_scenarios as supported_verification_scenarios,
)
from project_pipeline.verification import (
    verify_report as verification_verify_report,
)
from project_pipeline.verification.impact import (
    derive_test_impact as verification_derive_test_impact,
)


def _root(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise argparse.ArgumentTypeError(f"Repository root does not exist: {value}")
    return path


def _add_configuration_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile")
    parser.add_argument("--config-file", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a nested configuration key; may be repeated",
    )


def _write_json_output(value: Any, output: Path | None) -> None:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    print(text, end="")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Inspect local bootstrap prerequisites")
    doctor.add_argument("--root", type=_root, default=Path.cwd())
    _add_configuration_arguments(doctor)

    config = commands.add_parser("config", help="Load and validate layered runtime configuration")
    config.add_argument("action", choices=("show", "validate"))
    config.add_argument("--root", type=_root, default=Path.cwd())
    config.add_argument("--json-output", type=Path)
    _add_configuration_arguments(config)

    bootstrap = commands.add_parser("bootstrap", help="Run deterministic runtime diagnostics")
    bootstrap.add_argument("--root", type=_root, default=Path.cwd())
    bootstrap.add_argument("--prepare", action="store_true")
    bootstrap.add_argument("--skip-repository-validation", action="store_true")
    bootstrap.add_argument("--json-output", type=Path)
    _add_configuration_arguments(bootstrap)

    smoke = commands.add_parser("smoke", help="Execute the local idempotent foundation slice")
    smoke.add_argument("--root", type=_root, default=Path.cwd())
    smoke.add_argument("--json-output", type=Path)
    _add_configuration_arguments(smoke)

    schemas = commands.add_parser("schemas", help="Regenerate or validate typed JSON schemas")
    schemas.add_argument("action", choices=("write", "check"))
    schemas.add_argument("--root", type=_root, default=Path.cwd())

    dependencies = commands.add_parser(
        "dependencies", help="Validate or inspect deterministic dependency state"
    )
    dependencies.add_argument("action", choices=("status", "lock", "validate", "snapshot"))
    dependencies.add_argument("--root", type=_root, default=Path.cwd())
    dependencies.add_argument("--json-output", type=Path)
    dependencies.add_argument("--verify-installed", action="store_true")

    quality = commands.add_parser("quality", help="Run local and CI quality checks")
    quality.add_argument("--root", type=_root, default=Path.cwd())
    quality.add_argument("--strict-tools", action="store_true")
    quality.add_argument("--coverage", action="store_true")
    quality.add_argument("--json-output", type=Path)

    validate = commands.add_parser("validate", help="Run repository-contract validation")
    validate.add_argument("--root", type=_root, default=Path.cwd())
    validate.add_argument("--json-output", type=Path)

    manifest = commands.add_parser("manifest", help="Generate deterministic file manifests")
    manifest.add_argument("--root", type=_root, default=Path.cwd())

    repo_map = commands.add_parser("map", help="Generate compact repository maps")
    repo_map.add_argument("--root", type=_root, default=Path.cwd())

    line_plans = commands.add_parser("line-plans", help="Generate line-addressable plan copies")
    line_plans.add_argument("--root", type=_root, default=Path.cwd())

    coverage = commands.add_parser("coverage", help="Generate requirement coverage reports")
    coverage.add_argument("--root", type=_root, default=Path.cwd())

    requirements = commands.add_parser("requirements", help="Query the requirement catalog")
    requirements.add_argument("--root", type=_root, default=Path.cwd())
    requirements.add_argument("--id")
    requirements.add_argument("--domain")
    requirements.add_argument("--state")
    requirements.add_argument("--disposition")
    requirements.add_argument("--priority")
    requirements.add_argument("--source")
    requirements.add_argument("--text")
    requirements.add_argument("--summary", action="store_true")

    jira_rebuild = commands.add_parser("jira-rebuild", help="Rebuild Jira indexes and graph")
    jira_rebuild.add_argument("--root", type=_root, default=Path.cwd())

    requirement_views = commands.add_parser(
        "requirement-views", help="Regenerate human-readable requirement registry views"
    )
    requirement_views.add_argument("--root", type=_root, default=Path.cwd())

    architecture = commands.add_parser(
        "architecture", help="Query the target architecture and technology stack"
    )
    architecture.add_argument("--root", type=_root, default=Path.cwd())
    architecture.add_argument("--component")
    architecture.add_argument("--layer")
    architecture.add_argument("--state")
    architecture.add_argument("--text")
    architecture.add_argument("--stack", action="store_true")
    architecture.add_argument("--summary", action="store_true")
    architecture.add_argument("--write-views", action="store_true")

    state = commands.add_parser("state", help="Manage deterministic project and task state")
    state.add_argument(
        "action",
        choices=(
            "init",
            "status",
            "project",
            "task",
            "transition-project",
            "transition-task",
            "migrations",
        ),
    )
    state.add_argument("--root", type=_root, default=Path.cwd())
    state.add_argument("--database", type=Path)
    state.add_argument("--project-id")
    state.add_argument("--task-id")
    state.add_argument("--next-state")
    state.add_argument("--expected-version", type=int)
    state.add_argument("--reason", default="Operator-requested deterministic state transition.")
    state.add_argument("--actor-id", default="actor:local-operator")
    state.add_argument("--correlation-id", default="corr:local-state-command")
    state.add_argument("--blocked-reason")
    state.add_argument("--owner-id")
    state.add_argument("--json-output", type=Path)
    _add_configuration_arguments(state)

    trace_store = commands.add_parser(
        "trace-store", help="Import, query, mutate, and export transactional traceability state"
    )
    trace_store.add_argument(
        "action",
        choices=("init", "status", "requirement", "source", "target", "add", "remove", "export"),
    )
    trace_store.add_argument("--root", type=_root, default=Path.cwd())
    trace_store.add_argument("--database", type=Path)
    trace_store.add_argument("--requirement-id")
    trace_store.add_argument("--source-reference")
    trace_store.add_argument(
        "--link-type", choices=tuple(item.value for item in TraceabilityLinkType)
    )
    trace_store.add_argument("--target")
    trace_store.add_argument("--expected-revision", type=int)
    trace_store.add_argument("--actor-id", default="actor:local-operator")
    trace_store.add_argument("--correlation-id", default="corr:local-trace-command")
    trace_store.add_argument(
        "--reason", default="Operator-requested traceability projection change."
    )
    trace_store.add_argument("--output", type=Path)
    trace_store.add_argument("--json-output", type=Path)
    _add_configuration_arguments(trace_store)

    intake = commands.add_parser(
        "intake", help="Inspect, compile, and bootstrap a new or existing project"
    )
    intake.add_argument(
        "action", choices=("inspect", "compile", "map", "gaps", "bootstrap", "status")
    )
    intake.add_argument("--root", type=_root, default=Path.cwd())
    intake.add_argument("--target-root", type=Path)
    intake.add_argument("--mode", choices=tuple(item.value for item in IntakeMode))
    intake.add_argument("--project-name")
    intake.add_argument("--project-id")
    intake.add_argument(
        "--scale",
        choices=tuple(item.value for item in ProjectScale),
        default=ProjectScale.STANDARD.value,
    )
    intake.add_argument(
        "--project-profile",
        dest="project_profiles",
        action="append",
        default=[],
        choices=tuple(item.value for item in ProjectProfile),
    )
    intake.add_argument("--canonical-url")
    intake.add_argument("--allow-nested-repositories", action="store_true")
    intake.add_argument("--max-files", type=int, default=20_000)
    intake.add_argument("--max-total-bytes", type=int, default=2_000_000_000)
    intake.add_argument("--max-hash-bytes-per-file", type=int, default=16_000_000)
    intake.add_argument("--database", type=Path)
    intake.add_argument("--compilation-id")
    intake.add_argument("--apply", action="store_true")
    intake.add_argument("--confirm-existing", action="store_true")
    intake.add_argument("--no-persist", action="store_true")
    intake.add_argument("--bundle-dir", type=Path)
    intake.add_argument("--replace-output", action="store_true")
    intake.add_argument("--actor-id", default="actor:local-intake")
    intake.add_argument("--correlation-id", default="corr:local-intake")
    intake.add_argument("--json-output", type=Path)
    _add_configuration_arguments(intake)

    jira = commands.add_parser(
        "jira", help="Validate, diff, export, and safely synchronize the Jira mirror"
    )
    jira.add_argument(
        "action",
        choices=(
            "validate",
            "export",
            "import-diff",
            "snapshot",
            "plan",
            "sync",
            "status",
            "comment",
        ),
    )
    jira.add_argument("--root", type=_root, default=Path.cwd())
    jira.add_argument("--database", type=Path)
    jira.add_argument("--project-key", default="PP")
    jira.add_argument("--provider", choices=("mock", "atlassian"), default="mock")
    jira.add_argument("--authority-mode", choices=tuple(item.value for item in JiraAuthorityMode))
    jira.add_argument("--remote-snapshot", type=Path)
    jira.add_argument("--plan-file", type=Path)
    jira.add_argument("--input", type=Path)
    jira.add_argument("--output", type=Path)
    jira.add_argument("--apply", action="store_true")
    jira.add_argument("--approve", action="store_true")
    jira.add_argument("--authorization-id")
    jira.add_argument("--actor-id", default="actor:local-jira")
    jira.add_argument("--correlation-id", default="corr:local-jira")
    jira.add_argument("--local-id")
    jira.add_argument("--comment-kind", choices=tuple(item.value for item in JiraCommentKind))
    jira.add_argument("--comment-body")
    jira.add_argument("--evidence-reference", action="append", default=[])
    jira.add_argument("--decision-reference", action="append", default=[])
    jira.add_argument("--json-output", type=Path)
    _add_configuration_arguments(jira)

    repository = commands.add_parser(
        "repository", help="Inspect and safely govern local Git branches and worktrees"
    )
    repository.add_argument(
        "action",
        choices=(
            "inspect",
            "branches",
            "worktrees",
            "guardian",
            "claim",
            "create-branch",
            "create-worktree",
            "remove-worktree",
            "cleanup",
        ),
    )
    repository.add_argument("--root", type=_root, default=Path.cwd())
    repository.add_argument("--repository-root", type=Path)
    repository.add_argument("--database", type=Path)
    repository.add_argument("--resource-kind", choices=tuple(item.value for item in OwnershipKind))
    repository.add_argument("--resource")
    repository.add_argument("--owner-task-id")
    repository.add_argument("--workspace-id")
    repository.add_argument("--branch")
    repository.add_argument("--start-point", default="HEAD")
    repository.add_argument("--worktree-path", type=Path)
    repository.add_argument("--apply", action="store_true")
    repository.add_argument("--approve", action="store_true")
    repository.add_argument("--actor-id", default="actor:local-repository")
    repository.add_argument("--correlation-id", default="corr:local-repository")
    repository.add_argument("--json-output", type=Path)
    _add_configuration_arguments(repository)

    github = commands.add_parser(
        "github", help="Inspect pull requests and evaluate or apply governed GitHub operations"
    )
    github.add_argument(
        "action", choices=("status", "snapshot", "pull", "merge-gate", "merge", "cleanup")
    )
    github.add_argument("--root", type=_root, default=Path.cwd())
    github.add_argument("--repository-root", type=Path)
    github.add_argument("--repository-slug")
    github.add_argument("--database", type=Path)
    github.add_argument("--provider", choices=("mock", "github"), default="mock")
    github.add_argument("--pull-number", type=int)
    github.add_argument("--required-check", action="append", default=[])
    github.add_argument("--approvals-required", type=int)
    github.add_argument("--merge-method", choices=("merge", "squash", "rebase"), default="squash")
    github.add_argument("--apply", action="store_true")
    github.add_argument("--approve", action="store_true")
    github.add_argument("--authorization-id")
    github.add_argument("--actor-id", default="actor:local-github")
    github.add_argument("--correlation-id", default="corr:local-github")
    github.add_argument("--json-output", type=Path)
    _add_configuration_arguments(github)

    control = commands.add_parser(
        "control", help="Evaluate deterministic project control and build sequencing"
    )
    control.add_argument(
        "action",
        choices=(
            "evaluate",
            "sequence",
            "readiness",
            "scope",
            "completion",
            "ready-plan",
            "ready-apply",
            "status",
        ),
    )
    control.add_argument("--root", type=_root, default=Path.cwd())
    control.add_argument("--database", type=Path)
    control.add_argument("--project-id")
    control.add_argument(
        "--task-id",
        action="append",
        help="Limit ready-plan or ready-apply to a specific task; may be repeated",
    )
    control.add_argument("--apply", action="store_true")
    control.add_argument("--approve", action="store_true")
    control.add_argument("--actor-id", default="actor:local-control")
    control.add_argument("--correlation-id", default="corr:local-control")
    control.add_argument("--json-output", type=Path)
    _add_configuration_arguments(control)

    scheduler = commands.add_parser(
        "scheduler", help="Plan conflict-safe dynamic lanes and govern local resource leases"
    )
    scheduler.add_argument(
        "action",
        choices=(
            "plan",
            "resources",
            "leases",
            "status",
            "simulate",
            "acquire",
            "renew",
            "release",
        ),
    )
    scheduler.add_argument("--root", type=_root, default=Path.cwd())
    scheduler.add_argument("--database", type=Path)
    scheduler.add_argument("--project-id")
    scheduler.add_argument("--max-lanes", type=int)
    scheduler.add_argument("--signals-file", type=Path)
    scheduler.add_argument("--task-id")
    scheduler.add_argument("--holder-id", default="actor:local-scheduler")
    scheduler.add_argument("--lease-id")
    scheduler.add_argument("--fencing-token", type=int)
    scheduler.add_argument("--ttl-seconds", type=int, default=900)
    scheduler.add_argument("--apply", action="store_true")
    scheduler.add_argument("--approve", action="store_true")
    scheduler.add_argument("--actor-id", default="actor:local-scheduler")
    scheduler.add_argument("--correlation-id", default="corr:local-scheduler")
    scheduler.add_argument("--json-output", type=Path)
    _add_configuration_arguments(scheduler)

    takeover = commands.add_parser(
        "takeover",
        help="Write governed durable takeover attestation and provider qualification records",
    )
    takeover.add_argument(
        "action",
        choices=("write-attestation", "write-provider-qualification"),
    )
    takeover.add_argument("--root", type=_root, default=Path.cwd())
    takeover.add_argument("--project-id")
    takeover.add_argument("--provider-id", default="provider:cursor-cli")
    takeover.add_argument("--scope", default="local-governed-phase1")
    takeover.add_argument("--evidence-ref", required=True)
    takeover.add_argument("--json-output", type=Path)
    _add_configuration_arguments(takeover)

    agent_router = commands.add_parser(
        "agent-router", help="Inspect capability registries and evaluate provider-neutral routing"
    )
    agent_router.add_argument("action", choices=("status", "registry", "route", "simulate"))
    agent_router.add_argument("--root", type=_root, default=Path.cwd())
    agent_router.add_argument("--database", type=Path)
    agent_router.add_argument("--task-id", default="TASK-ROUTE-PREVIEW")
    agent_router.add_argument("--task-class", default="reasoning")
    agent_router.add_argument("--capability", action="append", default=[])
    agent_router.add_argument("--quality-tier", default="standard")
    agent_router.add_argument(
        "--instructions",
        default="Evaluate the provider-neutral route without executing external work.",
    )
    agent_router.add_argument("--deny-data-egress", action="store_true")
    agent_router.add_argument("--allow-canary", action="store_true")
    agent_router.add_argument("--no-degraded", action="store_true")
    agent_router.add_argument("--json-output", type=Path)
    _add_configuration_arguments(agent_router)

    context = commands.add_parser(
        "context", help="Compile, inspect, and receipt immutable delegation context packs"
    )
    context.add_argument(
        "action", choices=("compile", "status", "pack", "receipt", "telemetry", "review")
    )
    context.add_argument("--root", type=_root, default=Path.cwd())
    context.add_argument("--database", type=Path)
    context.add_argument("--envelope", type=Path)
    context.add_argument("--candidates", type=Path)
    context.add_argument("--policy", type=Path)
    context.add_argument("--pack-id")
    context.add_argument("--worker-id")
    context.add_argument("--receipt-status", choices=tuple(item.value for item in ReceiptStatus))
    context.add_argument("--omission", action="append", default=[])
    context.add_argument("--conflict", action="append", default=[])
    context.add_argument("--request-context", action="append", default=[])
    context.add_argument(
        "--provider-egress",
        choices=tuple(item.value for item in ProviderEgress),
        default=ProviderEgress.LOCAL_ONLY.value,
    )
    context.add_argument("--artifact-root", type=Path)
    context.add_argument("--json-output", type=Path)
    _add_configuration_arguments(context)

    orchestration = commands.add_parser(
        "orchestration", help="Inspect and operate durable workflow/recovery state"
    )
    orchestration.add_argument(
        "action",
        choices=(
            "status",
            "backend-status",
            "register",
            "start",
            "query",
            "signal",
            "checkpoint",
            "heartbeat",
            "recover",
            "cancel",
            "resume",
            "simulate",
        ),
    )
    orchestration.add_argument("--root", type=_root, default=Path.cwd())
    orchestration.add_argument("--database", type=Path)
    orchestration.add_argument("--definition", type=Path)
    orchestration.add_argument("--definition-id")
    orchestration.add_argument("--workflow-id")
    orchestration.add_argument("--workflow-name")
    orchestration.add_argument("--idempotency-key")
    orchestration.add_argument("--input", type=Path)
    orchestration.add_argument("--payload", type=Path)
    orchestration.add_argument(
        "--backend",
        choices=tuple(item.value for item in DurableBackendKind),
        default=DurableBackendKind.LOCAL_REFERENCE.value,
    )
    orchestration.add_argument("--signal-name")
    orchestration.add_argument("--worker-id")
    orchestration.add_argument("--fencing-epoch", type=int)
    orchestration.add_argument("--ttl-seconds", type=int, default=60)
    orchestration.add_argument("--scenario", choices=supported_scenarios())
    orchestration.add_argument("--apply", action="store_true")
    orchestration.add_argument("--approve", action="store_true")
    orchestration.add_argument("--json-output", type=Path)
    _add_configuration_arguments(orchestration)

    budget = commands.add_parser(
        "budget", help="Inspect and operate deterministic budget, quota, and spend-lease state"
    )
    budget.add_argument(
        "action",
        choices=(
            "status",
            "limit",
            "quota",
            "admit",
            "reserve",
            "settle",
            "unknown",
            "reconcile-no-effect",
            "forecast",
            "metrics",
            "anomaly",
            "impact",
            "preflight",
            "simulate",
        ),
    )
    budget.add_argument("--root", type=_root, default=Path.cwd())
    budget.add_argument("--database", type=Path)
    budget.add_argument("--project-id", default="PROJECT-PIPELINE")
    budget.add_argument("--cycle-id", default="default")
    budget.add_argument("--limit", type=Path)
    budget.add_argument("--old-limit", type=Path)
    budget.add_argument("--quota", type=Path)
    budget.add_argument("--request", type=Path)
    budget.add_argument("--decision", type=Path)
    budget.add_argument("--entry", type=Path)
    budget.add_argument("--lease-id")
    budget.add_argument("--idempotency-key")
    budget.add_argument("--task-class")
    budget.add_argument("--provider-id")
    budget.add_argument("--p50-microunits", type=int, default=0)
    budget.add_argument("--p90-microunits", type=int)
    budget.add_argument("--queued-task-count", type=int, default=0)
    budget.add_argument("--burn-rate-microunits-per-day", type=int, default=0)
    budget.add_argument("--pace-ratio-milli", type=int, default=1000)
    budget.add_argument("--remaining-budget-microunits", type=int)
    budget.add_argument("--forecast-p90-microunits", type=int, default=0)
    budget.add_argument("--expected-p90-microunits", type=int)
    budget.add_argument("--observed-microunits", type=int)
    budget.add_argument("--path", type=Path)
    budget.add_argument("--allow-external-read", action="store_true")
    budget.add_argument("--scenario", choices=supported_budget_scenarios())
    budget.add_argument("--apply", action="store_true")
    budget.add_argument("--approve", action="store_true")
    budget.add_argument("--json-output", type=Path)
    _add_configuration_arguments(budget)

    assurance = commands.add_parser(
        "assurance", help="Inspect deterministic execution assurance and Completion Gate state"
    )
    assurance.add_argument(
        "action",
        choices=(
            "status",
            "compile",
            "completion-gate",
            "candidate",
            "loop-guard",
            "delivery-gate",
            "scope-change",
            "simulate",
        ),
    )
    assurance.add_argument("--root", type=_root, default=Path.cwd())
    assurance.add_argument("--database", type=Path)
    assurance.add_argument("--project-id", default="PROJECT-PIPELINE")
    assurance.add_argument("--input", type=Path)
    assurance.add_argument("--base-ref")
    assurance.add_argument("--head-ref", default="HEAD")
    assurance.add_argument("--scope", type=Path)
    assurance.add_argument("--requested-behavior", action="append", default=[])
    assurance.add_argument("--requested-path", action="append", default=[])
    assurance.add_argument("--scenario", choices=supported_assurance_scenarios())
    assurance.add_argument(
        "--record", action="store_true", help="Persist the deterministic assurance decision"
    )
    assurance.add_argument("--apply", action="store_true")
    assurance.add_argument("--approve", action="store_true")
    assurance.add_argument("--json-output", type=Path)
    _add_configuration_arguments(assurance)

    verification = commands.add_parser(
        "verification", help="Run profile-driven verification and golden-journey evidence"
    )
    verification.add_argument(
        "action",
        choices=("status", "tools", "plan", "impact", "journeys", "browser", "run", "simulate"),
    )
    verification.add_argument("--root", type=_root, default=Path.cwd())
    verification.add_argument("--database", type=Path)
    verification.add_argument("--project-id", default="PROJECT-PIPELINE")
    verification.add_argument("--scenario", choices=supported_verification_scenarios())
    verification.add_argument("--changed-path", action="append", default=[])
    verification.add_argument("--dependency-path", action="append", default=[])
    verification.add_argument("--requirement-id", action="append", default=[])
    verification.add_argument(
        "--risk", choices=("LOW", "MEDIUM", "HIGH", "CRITICAL"), default="MEDIUM"
    )
    verification.add_argument("--acceptance-method", action="append", default=[])
    verification.add_argument("--apply", action="store_true")
    verification.add_argument("--approve", action="store_true")
    verification.add_argument("--json-output", type=Path)
    _add_configuration_arguments(verification)

    security = commands.add_parser(
        "security", help="Inspect deterministic security, secret metadata, and supply-chain state"
    )
    security.add_argument(
        "action",
        choices=(
            "status",
            "tools",
            "root-trust",
            "sbom",
            "supply-chain",
            "self-modification",
            "record-identity",
            "simulate",
        ),
    )
    security.add_argument("--root", type=_root, default=Path.cwd())
    security.add_argument("--database", type=Path)
    security.add_argument("--project-id", default="PROJECT-PIPELINE")
    security.add_argument("--input", type=Path)
    security.add_argument("--changed-path", action="append", default=[])
    security.add_argument("--scenario", choices=supported_security_scenarios())
    security.add_argument("--apply", action="store_true")
    security.add_argument("--approve", action="store_true")
    security.add_argument("--json-output", type=Path)
    _add_configuration_arguments(security)

    resilience = commands.add_parser(
        "resilience",
        help="Inspect deterministic resilience, local-runtime, backup, and recovery state",
    )
    resilience.add_argument(
        "action",
        choices=(
            "status",
            "tools",
            "simulate",
            "local-runtime",
            "backup-plan",
            "restore-plan",
            "aws-plan",
        ),
    )
    resilience.add_argument("--root", type=_root, default=Path.cwd())
    resilience.add_argument("--database", type=Path)
    resilience.add_argument("--scenario", choices=supported_resilience_scenarios())
    resilience.add_argument("--domain")
    resilience.add_argument("--source")
    resilience.add_argument("--repository", default=".local/backups")
    resilience.add_argument("--target")
    resilience.add_argument("--capability", action="append", default=[])
    resilience.add_argument("--json-output", type=Path)
    _add_configuration_arguments(resilience)

    upstream = commands.add_parser("upstream", help="Query upstream review and adoption records")
    upstream.add_argument("--root", type=_root, default=Path.cwd())
    upstream.add_argument("--id")
    upstream.add_argument("--repository")
    upstream.add_argument("--disposition")
    upstream.add_argument("--inspection-state")
    upstream.add_argument("--subsystem")
    upstream.add_argument("--text")
    upstream.add_argument("--summary", action="store_true")
    upstream.add_argument("--convergence", action="store_true")
    upstream.add_argument("--write-views", action="store_true")

    archive = commands.add_parser("archive", help="Create a deterministic project ZIP")
    archive.add_argument("--root", type=_root, default=Path.cwd())
    archive.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify-archive", help="Verify ZIP integrity and root structure")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--expected-root")
    verify.add_argument(
        "--source-bearing",
        action="store_true",
        help="Skip permanent-repository terminology enforcement for a source continuation archive",
    )
    return parser


def _load_configuration(args: argparse.Namespace):
    return load_runtime_configuration(
        args.root,
        profile=args.profile,
        config_file=args.config_file,
        env_file=args.env_file,
        overrides=tuple(args.overrides),
    )


def _state_database_path(args: argparse.Namespace, configuration: Any) -> Path | str:
    if configuration.settings.persistence.backend is not PersistenceBackend.SQLITE_LOCAL:
        raise ConfigurationError(
            "Local state commands currently require the SQLITE_LOCAL profile; "
            "the PostgreSQL production port and migrations are defined but not live-verified."
        )
    if args.database is not None:
        candidate = args.database
        if str(candidate) == ":memory:":
            return ":memory:"
        return candidate.resolve() if candidate.is_absolute() else (args.root / candidate).resolve()
    return configuration.settings.database_path(args.root)


def _require_argument(args: argparse.Namespace, name: str) -> Any:
    value = getattr(args, name)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ConfigurationError(f"--{name.replace('_', '-')} is required for {args.action}")
    return value


def _run_state_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    with SQLiteStateStore(database, args.root) as store:
        service = CoreStateService(store, args.root)
        if args.action == "init":
            service.initialize_from_repository(
                actor_id=args.actor_id, correlation_id=args.correlation_id
            )
            traceability = RequirementTraceabilityService(store, args.root)
            imported = traceability.import_authoritative_catalog()
            result = store.snapshot(configuration.settings.project_id)
            return {
                "database": str(database),
                "state": result,
                "traceability_import": imported,
                "equivalence_errors": traceability.verify_authoritative_equivalence(),
            }, 0
        store.initialize()
        if store.get_project_manifest(configuration.settings.project_id) is None:
            service.initialize_from_repository(
                actor_id=args.actor_id, correlation_id=args.correlation_id
            )
        project_id = args.project_id or configuration.settings.project_id
        if args.action == "status":
            return {"database": str(database), "state": store.snapshot(project_id)}, 0
        if args.action == "migrations":
            return {"database": str(database), "migrations": store.migration_status()}, 0
        if args.action == "project":
            state = store.get_project_state(project_id)
            return {
                "database": str(database),
                "project_state": None if state is None else state.model_dump(mode="json"),
            }, 0 if state else 1
        if args.action == "task":
            task_id = str(_require_argument(args, "task_id"))
            state = store.get_task_state(task_id)
            return {
                "database": str(database),
                "task_state": None if state is None else state.model_dump(mode="json"),
            }, 0 if state else 1
        if args.action == "transition-project":
            next_state = ProjectLifecycleState(str(_require_argument(args, "next_state")))
            expected = int(_require_argument(args, "expected_version"))
            state = store.transition_project(
                project_id=project_id,
                next_state=next_state,
                expected_version=expected,
                reason=args.reason,
                actor_id=args.actor_id,
                correlation_id=args.correlation_id,
                blocked_reason=args.blocked_reason,
            )
            return {"database": str(database), "project_state": state.model_dump(mode="json")}, 0
        task_id = str(_require_argument(args, "task_id"))
        next_state = TaskLifecycleState(str(_require_argument(args, "next_state")))
        expected = int(_require_argument(args, "expected_version"))
        state = store.transition_task(
            task_id=task_id,
            next_state=next_state,
            expected_version=expected,
            reason=args.reason,
            actor_id=args.actor_id,
            correlation_id=args.correlation_id,
            blocked_reason=args.blocked_reason,
            owner_id=args.owner_id,
        )
        return {"database": str(database), "task_state": state.model_dump(mode="json")}, 0


def _run_trace_store_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    with SQLiteStateStore(database, args.root) as store:
        service = RequirementTraceabilityService(store, args.root)
        if args.action == "init":
            imported = service.import_authoritative_catalog()
            status = service.status()
            return {
                "database": str(database),
                "import": imported,
                "status": status,
            }, 0 if not status["equivalence_errors"] else 1
        store.initialize()
        if args.action == "status":
            result = service.status()
            return {"database": str(database), **result}, 0 if not result[
                "equivalence_errors"
            ] else 1
        if args.action == "requirement":
            requirement_id = str(_require_argument(args, "requirement_id"))
            result = service.trace_requirement(requirement_id)
            return {"database": str(database), "trace": result}, 0 if result else 1
        if args.action == "source":
            source = str(_require_argument(args, "source_reference"))
            return {
                "database": str(database),
                "source_reference": source,
                "requirement_ids": list(service.requirements_for_source(source)),
            }, 0
        if args.action == "target":
            link_type = TraceabilityLinkType(str(_require_argument(args, "link_type")))
            target = str(_require_argument(args, "target"))
            return {
                "database": str(database),
                "link_type": link_type.value,
                "target": target,
                "requirement_ids": list(service.requirements_for_target(link_type, target)),
            }, 0
        if args.action == "export":
            output = args.output or (
                args.root / ".local" / "exports" / "requirements.proposed.jsonl"
            )
            if not output.is_absolute():
                output = (args.root / output).resolve()
            result = service.write_projection(output)
            return {"database": str(database), **result}, 0
        requirement_id = str(_require_argument(args, "requirement_id"))
        link_type = TraceabilityLinkType(str(_require_argument(args, "link_type")))
        target = str(_require_argument(args, "target"))
        expected_revision = int(_require_argument(args, "expected_revision"))
        mutation = TraceabilityMutation(
            requirement_id=requirement_id,
            operation="ADD" if args.action == "add" else "REMOVE",
            link_type=link_type,
            target=target,
            expected_revision=expected_revision,
            actor_id=args.actor_id,
            correlation_id=args.correlation_id,
            reason=args.reason,
        )
        return {"database": str(database), "mutation": service.mutate(mutation)}, 0


def _jira_adapter(args: argparse.Namespace, configuration: Any):
    if args.provider == "mock":
        adapter = MockJiraAdapter(project_key=args.project_key)
        if args.remote_snapshot is not None:
            path = args.remote_snapshot
            path = path.resolve() if path.is_absolute() else (args.root / path).resolve()
            snapshot = JiraRemoteSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
            for issue in snapshot.issues:
                adapter.seed_issue(
                    remote_key=issue.remote_key,
                    local_id=issue.local_id,
                    summary=issue.summary,
                    state=issue.normalized_state or JiraLifecycleState.BACKLOG,
                    issue_type=issue.normalized_issue_type or JiraIssueType.TASK,
                    description_text=issue.description_text,
                    labels=issue.labels,
                    parent_remote_key=issue.parent_remote_key,
                )
        return adapter
    settings = configuration.settings.integrations
    if not settings.jira_base_url or not settings.jira_user_email or not settings.jira_api_token:
        raise ConfigurationError(
            "Atlassian provider requires jira_base_url, jira_user_email, and jira_api_token references"
        )
    token = SecretResolver(args.root).resolve(settings.jira_api_token)
    return AtlassianJiraCloudAdapter(
        base_url=settings.jira_base_url,
        user_email=settings.jira_user_email,
        api_token=token,
    )


def _repository_root(args: argparse.Namespace) -> Path:
    candidate = args.repository_root or args.root
    path = (
        candidate.expanduser().resolve()
        if isinstance(candidate, Path)
        else Path(candidate).expanduser().resolve()
    )
    if not path.exists() or not path.is_dir():
        raise ConfigurationError(f"repository root does not exist: {path}")
    return path


def _github_adapter(args: argparse.Namespace, configuration: Any):
    if args.provider == "mock":
        return MockGitHubAdapter(repository_slug=args.repository_slug or "example/project")
    token_ref = configuration.settings.integrations.github_token
    if token_ref is None:
        raise ConfigurationError(
            "GitHub provider requires integrations.github_token as a secret reference"
        )
    token = SecretResolver(args.root).resolve(token_ref)
    return GitHubRestAdapter(token=token)


def _run_repository_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    local = LocalGitRepository(_repository_root(args))
    with GitHubStewardStore(database, args.root) as store:
        remote = MockGitHubAdapter(
            repository_slug=local.repository_slug(), branches=local.branches()
        )
        steward = RepositorySteward(local=local, remote=remote, store=store)
        if args.action == "inspect":
            return {"database": str(database), **steward.inspect_local()}, 0
        if args.action == "branches":
            return {"branches": [item.model_dump(mode="json") for item in local.branches()]}, 0
        if args.action == "worktrees":
            return {"worktrees": [item.model_dump(mode="json") for item in local.worktrees()]}, 0
        if args.action == "guardian":
            decision = steward.branch_guardian()
            return decision.model_dump(mode="json"), 0 if decision.safe_for_work else 1
        if args.action == "claim":
            claim = steward.claim_resource(
                resource_kind=OwnershipKind(str(_require_argument(args, "resource_kind"))),
                resource=str(_require_argument(args, "resource")),
                owner_task_id=str(_require_argument(args, "owner_task_id")),
                workspace_id=str(_require_argument(args, "workspace_id")),
            )
            return claim.model_dump(mode="json"), 0
        if args.action == "cleanup":
            return steward.cleanup_plan(local.repository_slug()), 0
        if args.apply and not args.approve:
            raise ConfigurationError(
                "local repository mutation requires both --apply and --approve"
            )
        if args.action == "create-branch":
            result = local.create_branch(
                str(_require_argument(args, "branch")), args.start_point, apply=args.apply
            )
            return result, 0
        if args.action == "create-worktree":
            result = local.create_worktree(
                Path(_require_argument(args, "worktree_path")),
                str(_require_argument(args, "branch")),
                apply=args.apply,
            )
            return result, 0
        result = local.remove_worktree(
            Path(_require_argument(args, "worktree_path")), apply=args.apply
        )
        return result, 0


def _run_github_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    local = LocalGitRepository(_repository_root(args))
    repository_slug = args.repository_slug or local.repository_slug()
    adapter = _github_adapter(args, configuration)
    with GitHubStewardStore(database, args.root) as store:
        steward = RepositorySteward(local=local, remote=adapter, store=store)
        if args.action == "status":
            return {"database": str(database), **store.status(repository_slug)}, 0
        if args.action == "snapshot":
            metadata = adapter.get_repository(repository_slug)
            branches = tuple(adapter.iter_branches(repository_slug))
            return {
                "repository": metadata.model_dump(mode="json"),
                "branches": [item.model_dump(mode="json") for item in branches],
            }, 0
        if args.action == "cleanup":
            return steward.cleanup_plan(repository_slug), 0
        number = int(_require_argument(args, "pull_number"))
        if args.action == "pull":
            pull = steward.pull_snapshot(repository_slug, number)
            return pull.model_dump(mode="json"), 0
        if args.action == "merge-gate":
            gate = steward.merge_gate(
                repository_slug,
                number,
                required_checks=tuple(args.required_check) if args.required_check else None,
                approvals_required=args.approvals_required,
            )
            return gate.model_dump(mode="json"), 0 if gate.state.value == "READY" else 1
        gate, operation = steward.plan_merge(
            repository_slug,
            number,
            actor_id=args.actor_id,
            correlation_id=args.correlation_id,
            method=args.merge_method,
        )
        if not args.apply:
            return {
                "mode": "DRY_RUN",
                "gate": gate.model_dump(mode="json"),
                "operation": operation.model_dump(mode="json"),
            }, 0 if gate.state.value == "READY" else 1
        if not args.approve or not args.authorization_id:
            raise ConfigurationError(
                "GitHub merge requires --apply, --approve, and --authorization-id"
            )
        if (
            args.provider == "github"
            and configuration.settings.security.external_writes_default
            is not ExternalWriteMode.REQUIRE_APPROVAL
        ):
            raise ConfigurationError(
                "live GitHub writes require security.external_writes_default=REQUIRE_APPROVAL"
            )
        intent = ActionIntent(
            actor_id=args.actor_id,
            authority="github.steward",
            target=repository_slug,
            operation="github.merge",
            idempotency_key=operation.idempotency_key,
            approval_state=ApprovalState.APPROVED,
            correlation_id=args.correlation_id,
            risk=RiskLevel.HIGH,
        )
        receipt = steward.apply_merge(
            operation, gate, action_intent=intent, authorization_id=args.authorization_id
        )
        return {
            "mode": "APPLY",
            "gate": gate.model_dump(mode="json"),
            "receipt": receipt.model_dump(mode="json"),
        }, 0 if receipt.state.value == "APPLIED" else 1


def _takeover_policy(root: Path) -> dict[str, Any]:
    path = root / "config" / "cursor_takeover.json"
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _canonical_evidence_ref(root: Path, evidence_path: Path) -> str:
    try:
        return evidence_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(evidence_path.resolve())


def _resolve_takeover_evidence(
    *,
    root: Path,
    evidence_ref: str,
    expected_project_id: str,
    expected_provider_id: str,
    expected_scope: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    reference = evidence_ref.strip()
    if not reference:
        return {
            "valid": False,
            "reasons": ["missing_evidence_reference"],
            "reference": evidence_ref,
            "canonical_ref": None,
            "resolved_path": None,
            "fingerprint": None,
            "payload": None,
        }
    candidate = Path(reference)
    evidence_path = candidate if candidate.is_absolute() else (root / candidate).resolve()
    resolved_path = str(evidence_path)
    if not evidence_path.is_file():
        reasons.append("missing_evidence_artifact")
        return {
            "valid": False,
            "reasons": reasons,
            "reference": evidence_ref,
            "canonical_ref": _canonical_evidence_ref(root, evidence_path),
            "resolved_path": resolved_path,
            "fingerprint": None,
            "payload": None,
        }
    try:
        body = evidence_path.read_bytes()
    except OSError:
        reasons.append("unreadable_evidence_artifact")
        return {
            "valid": False,
            "reasons": reasons,
            "reference": evidence_ref,
            "canonical_ref": _canonical_evidence_ref(root, evidence_path),
            "resolved_path": resolved_path,
            "fingerprint": None,
            "payload": None,
        }
    fingerprint = hashlib.sha256(body).hexdigest()
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        reasons.append("invalid_evidence_payload")
        payload = None
    if not isinstance(payload, dict):
        if "invalid_evidence_payload" not in reasons:
            reasons.append("invalid_evidence_payload")
        payload = None
    if isinstance(payload, dict) and (
        payload.get("project_id") != expected_project_id
        or payload.get("provider_id") != expected_provider_id
        or payload.get("scope") != expected_scope
    ):
        reasons.append("evidence_identity_mismatch")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "reference": evidence_ref,
        "canonical_ref": _canonical_evidence_ref(root, evidence_path),
        "resolved_path": resolved_path,
        "fingerprint": fingerprint,
        "payload": payload,
    }


def _takeover_attestation_path(root: Path) -> Path:
    override = Path(
        str(
            os.environ.get(
                "PROJECT_PIPELINE_TAKEOVER_ATTESTATION_PATH",
                root / ".local" / "state" / "takeover" / "privacy_attestation.json",
            )
        )
    )
    return override if override.is_absolute() else (root / override).resolve()


def _takeover_provider_qualification_path(root: Path) -> Path:
    explicit_override = os.environ.get("PROJECT_PIPELINE_PROVIDER_QUALIFICATION_PATH")
    if explicit_override:
        override = Path(str(explicit_override))
    else:
        attestation_override = os.environ.get("PROJECT_PIPELINE_TAKEOVER_ATTESTATION_PATH")
        if attestation_override:
            # Keep takeover artifacts lane-scoped when tests or workflows override only
            # the attestation path; this prevents accidental reuse of unrelated global state.
            override = Path(str(attestation_override)).with_name("provider_qualification.json")
        else:
            override = root / ".local" / "state" / "takeover" / "provider_qualification.json"
    return override if override.is_absolute() else (root / override).resolve()


def _load_durable_attestation(root: Path) -> tuple[DurableAttestation | None, str]:
    path = _takeover_attestation_path(root)
    if not path.is_file():
        return None, str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, str(path)
    if not isinstance(payload, dict):
        return None, str(path)
    fingerprint = payload.get("fingerprint")
    approved = payload.get("approved")
    if not isinstance(fingerprint, str) or not isinstance(approved, bool):
        return None, str(path)
    project_id = payload.get("project_id")
    provider_id = payload.get("provider_id")
    scope = payload.get("scope")
    approved_at_utc = payload.get("approved_at_utc")
    evidence_ref = payload.get("evidence_ref")
    evidence_fingerprint = payload.get("evidence_fingerprint")
    return (
        DurableAttestation(
            fingerprint=fingerprint,
            approved=approved,
            project_id=project_id if isinstance(project_id, str) else None,
            provider_id=provider_id if isinstance(provider_id, str) else None,
            scope=scope if isinstance(scope, str) else None,
            approved_at_utc=approved_at_utc if isinstance(approved_at_utc, str) else None,
            evidence_ref=evidence_ref if isinstance(evidence_ref, str) else None,
            evidence_fingerprint=(
                evidence_fingerprint if isinstance(evidence_fingerprint, str) else None
            ),
        ),
        str(path),
    )


def _load_provider_qualification_evidence(
    root: Path,
) -> tuple[DurableProviderQualificationEvidence | None, str]:
    path = _takeover_provider_qualification_path(root)
    if not path.is_file():
        return None, str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, str(path)
    if not isinstance(payload, dict):
        return None, str(path)
    qualified = payload.get("qualified")
    if not isinstance(qualified, bool):
        return None, str(path)
    fingerprint = payload.get("fingerprint")
    project_id = payload.get("project_id")
    provider_id = payload.get("provider_id")
    scope = payload.get("scope")
    verified_at_utc = payload.get("verified_at_utc")
    evidence_ref = payload.get("evidence_ref")
    evidence_fingerprint = payload.get("evidence_fingerprint")
    return (
        DurableProviderQualificationEvidence(
            qualified=qualified,
            fingerprint=fingerprint if isinstance(fingerprint, str) else None,
            project_id=project_id if isinstance(project_id, str) else None,
            provider_id=provider_id if isinstance(provider_id, str) else None,
            scope=scope if isinstance(scope, str) else None,
            verified_at_utc=verified_at_utc if isinstance(verified_at_utc, str) else None,
            evidence_ref=evidence_ref if isinstance(evidence_ref, str) else None,
            evidence_fingerprint=(
                evidence_fingerprint if isinstance(evidence_fingerprint, str) else None
            ),
        ),
        str(path),
    )


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def _takeover_evidence_reference_validation(
    *,
    root: Path,
    evidence_ref: str | None,
    evidence_fingerprint: str | None,
    expected_project_id: str,
    expected_provider_id: str,
    expected_scope: str,
    expected_timestamp_utc: str | None,
    max_age_hours: int | None,
    require_reference: bool,
    require_identity: bool,
    require_fingerprint: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    resolved_path: str | None = None
    actual_fingerprint: str | None = None
    fingerprint_matches = not require_fingerprint
    identity_matches = not require_identity
    fresh_within_policy = max_age_hours is None
    payload_is_json_object = False

    ref_value = evidence_ref.strip() if isinstance(evidence_ref, str) else ""
    if require_reference and not ref_value:
        reasons.append("missing_evidence_reference")
    evidence_path: Path | None = None
    if ref_value:
        candidate = Path(ref_value)
        evidence_path = candidate if candidate.is_absolute() else (root / candidate).resolve()
        resolved_path = str(evidence_path)
        if not evidence_path.is_file():
            reasons.append("missing_evidence_artifact")
            evidence_path = None

    evidence_payload: dict[str, Any] | None = None
    if evidence_path is not None:
        try:
            body = evidence_path.read_bytes()
        except OSError:
            reasons.append("unreadable_evidence_artifact")
            body = None
        if body is not None:
            actual_fingerprint = hashlib.sha256(body).hexdigest()
            if require_fingerprint:
                if not evidence_fingerprint:
                    reasons.append("missing_evidence_fingerprint")
                elif actual_fingerprint != evidence_fingerprint:
                    reasons.append("evidence_fingerprint_mismatch")
                else:
                    fingerprint_matches = True
            else:
                fingerprint_matches = True
            if require_identity or max_age_hours is not None:
                try:
                    loaded = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    reasons.append("invalid_evidence_payload")
                    loaded = None
                if isinstance(loaded, dict):
                    payload_is_json_object = True
                    evidence_payload = loaded

    if require_identity:
        if not payload_is_json_object:
            reasons.append("missing_evidence_identity_fields")
        else:
            project_ok = evidence_payload.get("project_id") == expected_project_id
            provider_ok = evidence_payload.get("provider_id") == expected_provider_id
            scope_ok = evidence_payload.get("scope") == expected_scope
            identity_matches = project_ok and provider_ok and scope_ok
            if not identity_matches:
                reasons.append("evidence_identity_mismatch")

    if max_age_hours is not None:
        fresh_within_policy = False
        observed_timestamp = _parse_utc_timestamp(expected_timestamp_utc)
        if observed_timestamp is None:
            reasons.append("missing_evidence_timestamp")
        else:
            now_utc = datetime.now(UTC)
            age_hours = (now_utc - observed_timestamp).total_seconds() / 3600
            fresh_within_policy = 0 <= age_hours <= max_age_hours
            if not fresh_within_policy:
                reasons.append("evidence_stale")

    valid = not reasons
    return {
        "valid": valid,
        "reference": evidence_ref,
        "resolved_path": resolved_path,
        "artifact_found": evidence_path is not None,
        "fingerprint_expected": evidence_fingerprint,
        "fingerprint_actual": actual_fingerprint,
        "fingerprint_matches": fingerprint_matches,
        "identity_matches": identity_matches,
        "fresh_within_policy": fresh_within_policy,
        "reasons": reasons,
    }


def _attestation_state_from_reasons(reasons: tuple[str, ...] | list[str]) -> AttestationState:
    if any(reason.endswith("_stale") for reason in reasons):
        return AttestationState.STALE
    if any("mismatch" in reason for reason in reasons):
        return AttestationState.MISMATCHED
    if any(reason.startswith("missing_") for reason in reasons):
        return AttestationState.MISSING
    return AttestationState.INVALID


def _provider_state_from_reasons(
    reasons: tuple[str, ...] | list[str],
) -> ProviderQualificationState:
    if any(reason.endswith("_stale") for reason in reasons):
        return ProviderQualificationState.STALE
    if any("mismatch" in reason for reason in reasons):
        return ProviderQualificationState.MISMATCHED
    if any(reason.startswith("missing_") for reason in reasons):
        return ProviderQualificationState.MISSING
    return ProviderQualificationState.INVALID


def _write_takeover_record(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(serialized, encoding="utf-8", newline="\n")


def _run_takeover_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    project_id = args.project_id or configuration.settings.project_id
    provider_id = str(args.provider_id)
    scope = str(args.scope)
    evidence = _resolve_takeover_evidence(
        root=args.root,
        evidence_ref=str(args.evidence_ref),
        expected_project_id=project_id,
        expected_provider_id=provider_id,
        expected_scope=scope,
    )
    if not evidence["valid"]:
        return {
            "ok": False,
            "action": args.action,
            "reasons": list(evidence["reasons"]),
            "evidence_reference": {
                "reference": evidence["reference"],
                "canonical_ref": evidence["canonical_ref"],
                "resolved_path": evidence["resolved_path"],
                "fingerprint": evidence["fingerprint"],
            },
        }, 1
    payload = evidence["payload"]
    assert isinstance(payload, dict)
    if args.action == "write-attestation":
        reasons: list[str] = []
        approved = payload.get("approved")
        if approved is not True:
            reasons.append("attestation_not_approved")
        approved_at_utc = payload.get("approved_at_utc")
        if not isinstance(approved_at_utc, str) or _parse_utc_timestamp(approved_at_utc) is None:
            reasons.append("missing_or_invalid_attestation_timestamp")
        if reasons:
            return {
                "ok": False,
                "action": args.action,
                "reasons": reasons,
                "evidence_reference": {
                    "reference": evidence["reference"],
                    "canonical_ref": evidence["canonical_ref"],
                    "resolved_path": evidence["resolved_path"],
                    "fingerprint": evidence["fingerprint"],
                },
            }, 1
        requires_privacy_attestation = bool(
            _takeover_policy(args.root).get(
                "require_privacy_mode", provider_id == "provider:cursor-cli"
            )
        )
        fingerprint = DurableAttestation.fingerprint_for(
            {
                "project_id": project_id,
                "provider_id": provider_id,
                "scope": scope,
                "requires_privacy_attestation": requires_privacy_attestation,
            }
        )
        record = {
            "fingerprint": fingerprint,
            "approved": True,
            "project_id": project_id,
            "provider_id": provider_id,
            "scope": scope,
            "approved_at_utc": approved_at_utc,
            "evidence_ref": evidence["canonical_ref"],
            "evidence_fingerprint": evidence["fingerprint"],
        }
        path = _takeover_attestation_path(args.root)
        _write_takeover_record(path, record)
        return {
            "ok": True,
            "action": args.action,
            "path": str(path),
            "record": record,
        }, 0
    reasons = []
    qualified = payload.get("qualified")
    if qualified is not True:
        reasons.append("provider_not_qualified")
    verified_at_utc = payload.get("verified_at_utc")
    if not isinstance(verified_at_utc, str) or _parse_utc_timestamp(verified_at_utc) is None:
        reasons.append("missing_or_invalid_provider_qualification_timestamp")
    if reasons:
        return {
            "ok": False,
            "action": args.action,
            "reasons": reasons,
            "evidence_reference": {
                "reference": evidence["reference"],
                "canonical_ref": evidence["canonical_ref"],
                "resolved_path": evidence["resolved_path"],
                "fingerprint": evidence["fingerprint"],
            },
        }, 1
    fingerprint = DurableProviderQualificationEvidence.fingerprint_for(
        project_id=project_id,
        provider_id=provider_id,
        scope=scope,
        qualified=True,
    )
    record = {
        "qualified": True,
        "fingerprint": fingerprint,
        "project_id": project_id,
        "provider_id": provider_id,
        "scope": scope,
        "verified_at_utc": verified_at_utc,
        "evidence_ref": evidence["canonical_ref"],
        "evidence_fingerprint": evidence["fingerprint"],
    }
    path = _takeover_provider_qualification_path(args.root)
    _write_takeover_record(path, record)
    return {
        "ok": True,
        "action": args.action,
        "path": str(path),
        "record": record,
    }, 0


def _takeover_governor_status(
    *,
    root: Path,
    project_id: str,
    provider_id: str,
    active_lane_count: int,
) -> dict[str, Any]:
    policy = _takeover_policy(root)
    requires_privacy_attestation = bool(
        policy.get("require_privacy_mode", provider_id == "provider:cursor-cli")
    )
    require_attestation_identity = bool(policy.get("attestation_require_identity", True))
    require_attestation_evidence_reference = bool(
        policy.get("attestation_require_evidence_reference", True)
    )
    require_attestation_evidence_fingerprint = bool(
        policy.get("attestation_require_evidence_fingerprint", True)
    )
    max_attestation_age_hours = policy.get("attestation_max_age_hours")
    if not isinstance(max_attestation_age_hours, int) or max_attestation_age_hours <= 0:
        max_attestation_age_hours = None
    require_provider_qualification_identity = bool(
        policy.get("provider_qualification_require_identity", True)
    )
    require_provider_qualification_fingerprint = bool(
        policy.get("provider_qualification_require_fingerprint", True)
    )
    require_provider_qualification_evidence_reference = bool(
        policy.get("provider_qualification_require_evidence_reference", True)
    )
    require_provider_qualification_evidence_fingerprint = bool(
        policy.get("provider_qualification_require_evidence_fingerprint", True)
    )
    max_provider_qualification_age_hours = policy.get("provider_qualification_max_age_hours")
    if (
        not isinstance(max_provider_qualification_age_hours, int)
        or max_provider_qualification_age_hours <= 0
    ):
        max_provider_qualification_age_hours = None
    provider_scope = "local-governed-phase1"
    attestation_inputs = {
        "project_id": project_id,
        "provider_id": provider_id,
        "scope": provider_scope,
        "requires_privacy_attestation": requires_privacy_attestation,
    }
    prior_attestation, attestation_path = _load_durable_attestation(root)
    prior_provider_qualification, provider_qualification_path = (
        _load_provider_qualification_evidence(root)
    )
    attestation_validation = validate_durable_attestation(
        prior=prior_attestation,
        attestation_inputs=attestation_inputs,
        require_identity=require_attestation_identity,
        max_age_hours=max_attestation_age_hours,
    )
    provider_qualification_validation = validate_provider_qualification_evidence(
        evidence=prior_provider_qualification,
        project_id=project_id,
        provider_id=provider_id,
        scope=provider_scope,
        require_identity=require_provider_qualification_identity,
        require_fingerprint=require_provider_qualification_fingerprint,
        max_age_hours=max_provider_qualification_age_hours,
    )
    attestation_reference_validation = _takeover_evidence_reference_validation(
        root=root,
        evidence_ref=None if prior_attestation is None else prior_attestation.evidence_ref,
        evidence_fingerprint=(
            None if prior_attestation is None else prior_attestation.evidence_fingerprint
        ),
        expected_project_id=project_id,
        expected_provider_id=provider_id,
        expected_scope=provider_scope,
        expected_timestamp_utc=None
        if prior_attestation is None
        else prior_attestation.approved_at_utc,
        max_age_hours=max_attestation_age_hours,
        require_reference=require_attestation_evidence_reference,
        require_identity=require_attestation_identity,
        require_fingerprint=require_attestation_evidence_fingerprint,
    )
    provider_reference_validation = _takeover_evidence_reference_validation(
        root=root,
        evidence_ref=(
            None
            if prior_provider_qualification is None
            else prior_provider_qualification.evidence_ref
        ),
        evidence_fingerprint=(
            None
            if prior_provider_qualification is None
            else prior_provider_qualification.evidence_fingerprint
        ),
        expected_project_id=project_id,
        expected_provider_id=provider_id,
        expected_scope=provider_scope,
        expected_timestamp_utc=(
            None
            if prior_provider_qualification is None
            else prior_provider_qualification.verified_at_utc
        ),
        max_age_hours=max_provider_qualification_age_hours,
        require_reference=require_provider_qualification_evidence_reference,
        require_identity=require_provider_qualification_identity,
        require_fingerprint=require_provider_qualification_evidence_fingerprint,
    )
    attestation_gate_reasons = tuple(
        [*attestation_validation.reasons, *attestation_reference_validation["reasons"]]
    )
    attestation_gate_valid = (
        attestation_validation.valid and attestation_reference_validation["valid"]
    )
    attestation_gate_state = (
        AttestationState.VALID
        if attestation_gate_valid
        else _attestation_state_from_reasons(attestation_gate_reasons)
    )
    provider_gate_reasons = tuple(
        [*provider_qualification_validation.reasons, *provider_reference_validation["reasons"]]
    )
    provider_qualification_satisfied = (
        provider_qualification_validation.satisfied and provider_reference_validation["valid"]
    )
    provider_qualification_state = (
        ProviderQualificationState.QUALIFIED
        if provider_qualification_satisfied
        else _provider_state_from_reasons(provider_gate_reasons)
    )
    request_human_attestation = not attestation_gate_valid
    provider_lane_state = scoped_lane_state(
        has_privacy_attestation=attestation_gate_valid,
        requires_privacy_attestation=requires_privacy_attestation,
        missing_external_credentials=False,
        depends_on_external_credentials=False,
        resource_collision=False,
    )
    provider_gate_blocked = provider_dispatch_blocked(
        session_identity=SessionIdentity.PROGRAMMATIC_CURSOR_CLI_WORKER,
        provider_id=provider_id,
        provider_qualified=provider_qualification_satisfied,
    )
    provider_dispatch_eligible = (
        attestation_gate_valid and provider_qualification_satisfied and not provider_gate_blocked
    )
    local_lane_state = LaneState.ACTIVE if active_lane_count > 0 else LaneState.BLOCKED
    lane_matrix = [
        {
            "lane_id": "lane:local-governed",
            "state": local_lane_state.value,
            "eligible_unrelated_work_count": active_lane_count,
        },
        {
            "lane_id": f"lane:{provider_id}",
            "state": provider_lane_state.value,
            "requires_privacy_attestation": requires_privacy_attestation,
        },
    ]
    return {
        "attestation": {
            "source": "durable_local_state",
            "path": attestation_path,
            "found": prior_attestation is not None,
            "approved": None if prior_attestation is None else prior_attestation.approved,
            "request_human_attestation": request_human_attestation,
            "state": attestation_gate_state.value,
            "reasons": list(attestation_gate_reasons),
            "fingerprint_matches": attestation_validation.fingerprint_matches,
            "identity_matches": attestation_validation.identity_matches,
            "fresh_within_policy": attestation_validation.fresh_within_policy,
            "max_age_hours": max_attestation_age_hours,
            "expected_fingerprint": DurableAttestation.fingerprint_for(attestation_inputs),
            "evidence_reference": attestation_reference_validation,
        },
        "provider_dispatch": {
            "provider_id": provider_id,
            "provider_qualification_satisfied": provider_qualification_satisfied,
            "blocked_by_provider_gate": provider_gate_blocked,
            "eligible": provider_dispatch_eligible,
            "state": (
                ProviderQualificationState.QUALIFIED.value
                if provider_dispatch_eligible
                else provider_qualification_state.value
            ),
            "reasons": list(provider_gate_reasons),
            "qualification_evidence": {
                "source": "durable_local_state",
                "path": provider_qualification_path,
                "found": prior_provider_qualification is not None,
                "qualified": (
                    None
                    if prior_provider_qualification is None
                    else prior_provider_qualification.qualified
                ),
                "fingerprint_matches": provider_qualification_validation.fingerprint_matches,
                "identity_matches": provider_qualification_validation.identity_matches,
                "fresh_within_policy": provider_qualification_validation.fresh_within_policy,
                "max_age_hours": max_provider_qualification_age_hours,
                "evidence_ref": (
                    None
                    if prior_provider_qualification is None
                    else prior_provider_qualification.evidence_ref
                ),
                "evidence_fingerprint": (
                    None
                    if prior_provider_qualification is None
                    else prior_provider_qualification.evidence_fingerprint
                ),
                "reference_validation": provider_reference_validation,
            },
        },
        "gate_reconciliation": {
            "input_fingerprint": hashlib.sha256(
                json.dumps(
                    {
                        "project_id": project_id,
                        "provider_id": provider_id,
                        "scope": provider_scope,
                        "attestation": None
                        if prior_attestation is None
                        else {
                            "fingerprint": prior_attestation.fingerprint,
                            "approved": prior_attestation.approved,
                            "project_id": prior_attestation.project_id,
                            "provider_id": prior_attestation.provider_id,
                            "scope": prior_attestation.scope,
                            "approved_at_utc": prior_attestation.approved_at_utc,
                            "evidence_ref": prior_attestation.evidence_ref,
                            "evidence_fingerprint": prior_attestation.evidence_fingerprint,
                        },
                        "provider_qualification": None
                        if prior_provider_qualification is None
                        else {
                            "qualified": prior_provider_qualification.qualified,
                            "fingerprint": prior_provider_qualification.fingerprint,
                            "project_id": prior_provider_qualification.project_id,
                            "provider_id": prior_provider_qualification.provider_id,
                            "scope": prior_provider_qualification.scope,
                            "verified_at_utc": prior_provider_qualification.verified_at_utc,
                            "evidence_ref": prior_provider_qualification.evidence_ref,
                            "evidence_fingerprint": prior_provider_qualification.evidence_fingerprint,
                        },
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "attestation_gate": {
                "state": attestation_gate_state.value,
                "eligible": attestation_gate_valid,
                "reasons": list(attestation_gate_reasons),
            },
            "provider_qualification_gate": {
                "state": provider_qualification_state.value,
                "eligible": provider_qualification_satisfied,
                "reasons": list(provider_gate_reasons),
            },
        },
        "lane_matrix": lane_matrix,
        "global_stop_required": global_stop_required(
            tuple(LaneState(row["state"]) for row in lane_matrix)
        ),
    }


def _load_product_outcome(root: Path) -> dict[str, Any] | None:
    path = root / "config" / "product_outcome.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _completion_stages(product_outcome: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    completion_semantics = product_outcome.get("completion_semantics")
    if not isinstance(completion_semantics, dict):
        return ()
    raw_stages = completion_semantics.get("stages")
    if not isinstance(raw_stages, list):
        return ()
    normalized: list[dict[str, Any]] = []
    for stage in raw_stages:
        if not isinstance(stage, dict):
            continue
        stage_id = stage.get("stage_id")
        order = stage.get("order")
        if not isinstance(stage_id, str) or not isinstance(order, int):
            continue
        story_ids = tuple(item for item in stage.get("jira_story_ids", []) if isinstance(item, str))
        normalized.append(
            {
                "stage_id": stage_id,
                "order": order,
                "story_ids": story_ids,
            }
        )
    return tuple(sorted(normalized, key=lambda item: (item["order"], item["stage_id"])))


def _apply_product_outcome_alignment(
    *,
    root: Path,
    action: str,
    snapshot: Any,
    result: dict[str, Any],
) -> None:
    product_outcome = _load_product_outcome(root)
    if product_outcome is None:
        return
    stages = _completion_stages(product_outcome)
    if not stages:
        return
    stage_by_story_id = {
        story_id: stage
        for stage in stages
        for story_id in stage.get("story_ids", ())
        if isinstance(story_id, str)
    }
    stage_counts = {stage["stage_id"]: 0 for stage in stages}
    stage_order = {stage["stage_id"]: stage["order"] for stage in stages}

    if action == "ready-plan":
        operations = list(result.get("operations", []))
        default_rank = max(stage_order.values(), default=0) + 1
        ranked: list[tuple[int, str, dict[str, Any]]] = []
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            task_id = str(operation.get("task_id", ""))
            stage = stage_by_story_id.get(task_id)
            if stage is not None:
                stage_counts[stage["stage_id"]] += 1
            ranked.append(
                (
                    stage["order"] if stage is not None else default_rank,
                    task_id,
                    operation,
                )
            )
        reordered = [item[2] for item in sorted(ranked, key=lambda entry: (entry[0], entry[1]))]
        result["operations"] = reordered
        mapped_story_ids = tuple(stage_by_story_id.keys())
        mapped_in_plan = [op for op in reordered if str(op.get("task_id")) in mapped_story_ids]
        result["product_outcome_alignment"] = {
            "source": "config/product_outcome.json",
            "stages": [
                {
                    "stage_id": stage["stage_id"],
                    "order": stage["order"],
                    "story_ids": list(stage["story_ids"]),
                    "planned_transition_count": stage_counts[stage["stage_id"]],
                }
                for stage in stages
            ],
            "operations_reordered_by_stage": [op.get("task_id") for op in operations]
            != [op.get("task_id") for op in reordered],
            "mapped_operation_count": len(mapped_in_plan),
            "unmapped_operation_count": max(len(reordered) - len(mapped_in_plan), 0),
            "non_competing_completion": True,
        }
        return

    readiness_by_task = {
        item.task_id: item for item in snapshot.readiness if hasattr(item, "task_id")
    }
    result["product_outcome_alignment"] = {
        "source": "config/product_outcome.json",
        "stages": [
            {
                "stage_id": stage["stage_id"],
                "order": stage["order"],
                "story_ids": list(stage["story_ids"]),
                "ready_story_ids": [
                    story_id
                    for story_id in stage["story_ids"]
                    if story_id in readiness_by_task and bool(readiness_by_task[story_id].ready)
                ],
            }
            for stage in stages
        ],
        "non_competing_completion": True,
    }


def _run_control_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    project_id = args.project_id or configuration.settings.project_id

    if args.action == "status":
        with ControlStore(database, args.root) as control_store:
            return {"database": str(database), "control": control_store.status(project_id)}, 0

    with SQLiteStateStore(database, args.root) as state_store:
        state_store.initialize()
        state_service = CoreStateService(state_store, args.root)
        if state_store.get_project_manifest(project_id) is None:
            state_service.initialize_from_repository(
                actor_id=args.actor_id, correlation_id=args.correlation_id
            )
        kernel = ProjectControlKernel(args.root, state_store, project_id)
        if args.action == "ready-apply":
            if not args.apply or not args.approve:
                raise ConfigurationError(
                    "ready-apply requires both --apply and --approve; control evaluation remains read-only by default"
                )
            applied = kernel.apply_readiness_transitions(
                actor_id=args.actor_id,
                correlation_id=args.correlation_id,
                task_ids=frozenset(args.task_id) if args.task_id else None,
            )
            state_service.refresh_task_counts(project_id)
            snapshot = kernel.evaluate()
            result: dict[str, Any] = {
                "database": str(database),
                "applied_transition_count": len(applied),
                "applied_transitions": applied,
                "snapshot": snapshot.model_dump(mode="json"),
            }
        else:
            snapshot = kernel.evaluate()
            if args.action == "evaluate":
                result = {"database": str(database), "snapshot": snapshot.model_dump(mode="json")}
            elif args.action == "sequence":
                result = {
                    "database": str(database),
                    "sequence": snapshot.sequence.model_dump(mode="json"),
                }
            elif args.action == "readiness":
                result = {
                    "database": str(database),
                    "eligibility": [item.model_dump(mode="json") for item in snapshot.eligibility],
                    "readiness": [item.model_dump(mode="json") for item in snapshot.readiness],
                }
            elif args.action == "scope":
                result = {
                    "database": str(database),
                    "scope": snapshot.scope.model_dump(mode="json"),
                }
            elif args.action == "completion":
                result = {
                    "database": str(database),
                    "completion": snapshot.completion.model_dump(mode="json"),
                }
            elif args.action == "ready-plan":
                result = {
                    "database": str(database),
                    "operations": list(
                        kernel.readiness_transition_plan(
                            task_ids=frozenset(args.task_id) if args.task_id else None
                        )
                    ),
                    "dry_run": True,
                }
            else:
                raise ConfigurationError(f"unsupported control action: {args.action}")

    _apply_product_outcome_alignment(
        root=args.root,
        action=args.action,
        snapshot=snapshot,
        result=result,
    )
    result["takeover_governor"] = _takeover_governor_status(
        root=args.root,
        project_id=project_id,
        provider_id="provider:cursor-cli",
        active_lane_count=snapshot.sequence.ready_count,
    )
    exit_code = 0
    if args.action == "completion":
        jira_sync_guard = evaluate_jira_sync_guard(args.root)
        result["jira_sync_guard"] = jira_sync_guard.as_dict()
        if not jira_sync_guard.passes:
            exit_code = 1

    with ControlStore(database, args.root) as control_store:
        control_store.save_snapshot(snapshot)
        result["control_status"] = control_store.status(project_id)
    return result, exit_code


def _run_scheduler_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    import shutil

    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    project_id = args.project_id or configuration.settings.project_id

    with SchedulerStore(database, args.root) as scheduler_store:
        scheduler_store.ensure_local_pools()
        if args.action == "status":
            return {"database": str(database), "scheduler": scheduler_store.status(project_id)}, 0
        if args.action == "resources":
            registry = scheduler_store.registry_snapshot()
            return {"database": str(database), "registry": registry.model_dump(mode="json")}, 0
        if args.action == "leases":
            return {
                "database": str(database),
                "active_leases": [
                    item.model_dump(mode="json") for item in scheduler_store.list_active_leases()
                ],
            }, 0
        if args.action in {"renew", "release"}:
            if not args.apply or not args.approve:
                raise ConfigurationError(
                    f"scheduler {args.action} requires both --apply and --approve"
                )
            if not args.lease_id or args.fencing_token is None:
                raise ConfigurationError(
                    f"scheduler {args.action} requires --lease-id and --fencing-token"
                )
            if args.action == "renew":
                lease = scheduler_store.renew_lease(
                    args.lease_id,
                    holder_id=args.holder_id,
                    fencing_token=args.fencing_token,
                    ttl_seconds=args.ttl_seconds,
                )
            else:
                lease = scheduler_store.release_lease(
                    args.lease_id,
                    holder_id=args.holder_id,
                    fencing_token=args.fencing_token,
                )
            return {"database": str(database), "lease": lease.model_dump(mode="json")}, 0

        with SQLiteStateStore(database, args.root) as state_store:
            state_store.initialize()
            state_service = CoreStateService(state_store, args.root)
            if state_store.get_project_manifest(project_id) is None:
                state_service.initialize_from_repository(
                    actor_id=args.actor_id, correlation_id=args.correlation_id
                )
            kernel = ProjectControlKernel(args.root, state_store, project_id)
            control = kernel.evaluate()

        profiles = profiles_from_repository(args.root, control)
        registry = scheduler_store.registry_snapshot()
        if args.signals_file:
            signal_path = (
                args.signals_file
                if args.signals_file.is_absolute()
                else args.root / args.signals_file
            )
            signals = BackpressureSignals.model_validate(
                json.loads(signal_path.read_text(encoding="utf-8"))
            )
        else:
            disk = shutil.disk_usage(args.root)
            disk_free_percent = (disk.free / disk.total * 100.0) if disk.total else None
            signals = BackpressureSignals(queue_depth=0, disk_free_percent=disk_free_percent)

        scheduler_engine = DynamicLaneScheduler()
        plan = scheduler_engine.plan(
            control,
            profiles,
            registry,
            signals=signals,
            max_lanes=args.max_lanes,
        )
        scheduler_store.save_plan(plan)
        takeover_governor = _takeover_governor_status(
            root=args.root,
            project_id=project_id,
            provider_id="provider:cursor-cli",
            active_lane_count=len(plan.lanes),
        )

        if args.action == "plan":
            return {
                "database": str(database),
                "control_snapshot_id": control.snapshot_id,
                "plan": plan.model_dump(mode="json"),
                "takeover_governor": takeover_governor,
                "dry_run": True,
            }, 0
        if args.action == "simulate":
            scenarios = (
                ("normal", BackpressureSignals(queue_depth=0)),
                ("congested", BackpressureSignals(queue_depth=50)),
                ("brownout", BackpressureSignals(queue_depth=200)),
                ("halt", BackpressureSignals(queue_depth=1000)),
            )
            results = []
            for name, scenario_signals in scenarios:
                result = simulate_scheduler_scenario(
                    name=name,
                    control=control,
                    profiles=profiles,
                    registry=registry,
                    signals=scenario_signals,
                )
                scheduler_store.save_simulation(result)
                results.append(result.model_dump(mode="json"))
            return {
                "database": str(database),
                "simulations": results,
                "takeover_governor": takeover_governor,
            }, 0
        if args.action == "acquire":
            if not args.apply or not args.approve:
                raise ConfigurationError("scheduler acquire requires both --apply and --approve")
            if not args.task_id:
                raise ConfigurationError("scheduler acquire requires --task-id")
            lane = next((item for item in plan.lanes if item.task_id == args.task_id), None)
            if lane is None:
                raise ConfigurationError(
                    "requested task is not admitted by the current scheduler plan"
                )
            bundle = scheduler_store.acquire_bundle(
                task_id=lane.task_id,
                holder_id=args.holder_id,
                claims=lane.claims,
                ttl_seconds=args.ttl_seconds,
            )
            return {
                "database": str(database),
                "plan_id": plan.plan_id,
                "lease_bundle": bundle.model_dump(mode="json"),
                "takeover_governor": takeover_governor,
            }, 0 if bundle.acquired else 1
        raise ConfigurationError(f"unsupported scheduler action: {args.action}")


def _run_agent_router_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    registry = load_agent_registry(args.root)
    with AgentRouterStore(database, args.root) as store:
        store.save_registry(registry)
        existing = {item.provider_id: item for item in store.provider_states()}
        states = []
        for provider in registry.providers:
            state = existing.get(provider.provider_id)
            if state is None:
                state = ProviderStateObservation(
                    provider_id=provider.provider_id,
                    state=(
                        ProviderRuntimeState.HEALTHY
                        if provider.enabled and provider.execution_mode.value == "MOCK"
                        else ProviderRuntimeState.DISABLED
                    ),
                    reason=(
                        "committed local mock provider"
                        if provider.enabled and provider.execution_mode.value == "MOCK"
                        else "external provider not activated"
                    ),
                    observed_at_utc=registry.generated_at_utc,
                )
                store.save_provider_state(state)
            states.append(state)
        circuits = list(store.circuits())
        by_circuit = {item.provider_id: item for item in circuits}
        for provider in registry.providers:
            if provider.provider_id not in by_circuit:
                record = CircuitBreakerRecord(
                    provider_id=provider.provider_id, updated_at_utc=registry.generated_at_utc
                )
                store.save_circuit(record)
                circuits.append(record)
        if args.action == "status":
            return {
                "database": str(database),
                "router": store.status(),
                "registry_id": registry.registry_id,
            }, 0
        if args.action == "registry":
            return {"database": str(database), "registry": registry.model_dump(mode="json")}, 0
        if args.action == "simulate":
            return {"database": str(database), "simulation": simulate_provider_failover()}, 0
        capabilities = tuple(args.capability or ["routine_reasoning"])
        contract = ExecutionTaskContract(
            task_id=args.task_id,
            task_class=args.task_class,
            required_capabilities=capabilities,
            quality_tier=args.quality_tier,
            instructions=args.instructions,
            allow_data_egress=not args.deny_data_egress,
            allow_degraded=not args.no_degraded,
            allow_canary=args.allow_canary,
        )
        decision = AgentRouter().route(contract, registry, states, circuits, store.performance())
        store.save_routing_decision(decision)
        return {
            "database": str(database),
            "routing_decision": decision.model_dump(mode="json"),
            "dry_run": True,
        }, 0 if decision.selected_provider_id else 1


def _run_jira_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.action == "validate":
        report = JiraMirrorRepository(args.root).validate()
        return report.as_dict(), 0 if report.valid else 1
    if args.action == "export":
        output = args.output or (args.root / ".local" / "exports" / "jira_mirror.json")
        output = output.resolve() if output.is_absolute() else (args.root / output).resolve()
        bundle = export_jira_mirror(args.root, output)
        return {
            "schema_version": "1.0.0",
            "output": str(output),
            "issue_count": bundle.issue_count,
            "edge_count": bundle.edge_count,
            "fingerprint": bundle.fingerprint,
        }, 0
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    adapter = _jira_adapter(args, configuration)
    authority_mode = JiraAuthorityMode(args.authority_mode) if args.authority_mode else None
    policy = load_jira_reconciliation_policy(args.root, authority_mode=authority_mode)
    with JiraSyncStore(database, args.root) as store:
        steward = JiraSteward(root=args.root, adapter=adapter, store=store, policy=policy)
        if args.action == "status":
            return {"database": str(database), **steward.status(args.project_key)}, 0
        if args.action == "import-diff":
            path = Path(_require_argument(args, "input"))
            path = path.resolve() if path.is_absolute() else (args.root / path).resolve()
            imported = load_jira_export(path)
            conflicts = steward.compare_import_bundle(imported)
            return {
                "database": str(database),
                "input": str(path),
                "conflicts": [item.model_dump(mode="json") for item in conflicts],
                "safe_to_import": not conflicts,
            }, 0 if not conflicts else 1
        if args.action == "snapshot":
            snapshot = steward.capture_remote_snapshot(args.project_key)
            if args.output:
                output = (
                    args.output.resolve()
                    if args.output.is_absolute()
                    else (args.root / args.output).resolve()
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
            return {
                "database": str(database),
                "snapshot": snapshot.model_dump(mode="json"),
                "output": str(args.output) if args.output else None,
            }, 0
        if args.action == "comment":
            local_id = str(_require_argument(args, "local_id"))
            kind = JiraCommentKind(str(_require_argument(args, "comment_kind")))
            body = str(_require_argument(args, "comment_body"))
            comment = JiraCommentIntent.create(
                local_id=local_id,
                kind=kind,
                body=body,
                actor_id=args.actor_id,
                correlation_id=args.correlation_id,
                evidence_references=tuple(args.evidence_reference),
                decision_references=tuple(args.decision_reference),
            )
            if not args.apply:
                return {
                    "database": str(database),
                    "mode": "DRY_RUN",
                    "comment_intent": comment.model_dump(mode="json"),
                }, 0
            if not args.approve or not args.authorization_id:
                raise ConfigurationError(
                    "comment application requires --apply, --approve, and --authorization-id"
                )
            if (
                args.provider == "atlassian"
                and configuration.settings.security.external_writes_default
                is not ExternalWriteMode.REQUIRE_APPROVAL
            ):
                raise ConfigurationError(
                    "live Atlassian writes require security.external_writes_default=REQUIRE_APPROVAL"
                )
            intent = ActionIntent(
                actor_id=args.actor_id,
                authority="jira.steward",
                target=local_id,
                operation="jira.comment",
                idempotency_key=f"jira-comment:{comment.comment_intent_id.lower()}",
                approval_state=ApprovalState.APPROVED,
                correlation_id=args.correlation_id,
                risk=RiskLevel.MEDIUM,
            )
            return {
                "database": str(database),
                "mode": "APPLY",
                **steward.post_comment(
                    comment,
                    action_intent=intent,
                    authorization_id=args.authorization_id,
                ),
            }, 0
        if args.plan_file is not None:
            path = (
                args.plan_file.resolve()
                if args.plan_file.is_absolute()
                else (args.root / args.plan_file).resolve()
            )
            plan = JiraReconciliationPlan.model_validate_json(path.read_text(encoding="utf-8"))
            snapshot = store.get_snapshot(plan.remote_snapshot_id)
            if snapshot is None:
                raise ConfigurationError(
                    f"plan snapshot is not present in synchronization store: {plan.remote_snapshot_id}"
                )
        else:
            plan = steward.plan(args.project_key)
        if args.output:
            output = (
                args.output.resolve()
                if args.output.is_absolute()
                else (args.root / args.output).resolve()
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        if args.action == "plan":
            return {
                "database": str(database),
                "plan": plan.model_dump(mode="json"),
                "output": str(args.output) if args.output else None,
            }, 0 if not plan.conflicts else 1
        if not args.apply:
            receipt = steward.dry_run(
                plan, actor_id=args.actor_id, correlation_id=args.correlation_id
            )
            return {
                "database": str(database),
                "plan": plan.model_dump(mode="json"),
                "receipt": receipt.model_dump(mode="json"),
            }, 0
        if not args.approve or not args.authorization_id:
            raise ConfigurationError(
                "synchronization application requires --apply, --approve, and --authorization-id"
            )
        if (
            args.provider == "atlassian"
            and configuration.settings.security.external_writes_default
            is not ExternalWriteMode.REQUIRE_APPROVAL
        ):
            raise ConfigurationError(
                "live Atlassian writes require security.external_writes_default=REQUIRE_APPROVAL"
            )
        intent = ActionIntent(
            actor_id=args.actor_id,
            authority="jira.steward",
            target=args.project_key,
            operation="jira.sync",
            scope=("jira:resolve-conflicts",) if plan.conflicts else (),
            idempotency_key=f"jira-sync:{plan.plan_id.lower()}",
            approval_state=ApprovalState.APPROVED,
            correlation_id=args.correlation_id,
            risk=RiskLevel.HIGH,
        )
        receipt = steward.apply(plan, action_intent=intent, authorization_id=args.authorization_id)
        return {
            "database": str(database),
            "plan_id": plan.plan_id,
            "receipt": receipt.model_dump(mode="json"),
        }, 0 if receipt.result == "APPLIED" else 1


def _run_intake_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    if args.action == "status":
        with SQLiteStateStore(database, args.root) as store:
            result = ProjectIntakeService(store).status(
                compilation_id=args.compilation_id, project_id=args.project_id
            )
        return {"database": str(database), **result}, 0 if result["found"] else 1

    target_root = Path(_require_argument(args, "target_root")).expanduser().resolve(strict=False)
    request = ProjectIntakeRequest(
        mode=IntakeMode(str(_require_argument(args, "mode"))),
        project_name=str(_require_argument(args, "project_name")),
        project_id=args.project_id,
        target_root=str(target_root),
        scale=ProjectScale(args.scale),
        requested_profiles=tuple(ProjectProfile(item) for item in args.project_profiles),
        canonical_url=args.canonical_url,
        allow_nested_repositories=args.allow_nested_repositories,
        max_files=args.max_files,
        max_total_bytes=args.max_total_bytes,
        max_hash_bytes_per_file=args.max_hash_bytes_per_file,
        actor_id=args.actor_id,
        correlation_id=args.correlation_id,
    )
    if args.action == "inspect":
        discovery = discover_repository(request)
        profile = detect_project_profile(discovery, request)
        return {
            "database": str(database),
            "schema_version": "1.0.0",
            "request_fingerprint": request.semantic_fingerprint(),
            "discovery": discovery.model_dump(mode="json"),
            "summary": discovery_summary(discovery),
            "profile_detection": profile.model_dump(mode="json"),
        }, 0

    # Compile before opening local persistence so a database path placed inside the
    # inspected project cannot become an accidental input to its own compilation.
    manifest = compile_project(request)
    persistence: dict[str, str | bool] | None = None
    if not args.no_persist:
        with SQLiteStateStore(database, args.root) as store:
            store.initialize()
            persistence = store.put_intake_compilation(
                manifest,
                actor_id=args.actor_id,
                correlation_id=args.correlation_id,
            )

    bundle: dict[str, str] | None = None
    if args.bundle_dir is not None:
        output = args.bundle_dir
        if not output.is_absolute():
            output = (args.root / output).resolve(strict=False)
        bundle = write_compilation_bundle(manifest, output, replace=args.replace_output)
    if args.action == "compile":
        return {
            "database": str(database),
            "compilation": manifest.model_dump(mode="json"),
            "persistence": persistence,
            "bundle": bundle,
        }, 0
    if args.action == "map":
        return {
            "database": str(database),
            "compilation_id": manifest.compilation_id,
            "repository_map": manifest.repository_map.model_dump(mode="json"),
            "persistence": persistence,
            "bundle": bundle,
        }, 0
    if args.action == "gaps":
        return {
            "database": str(database),
            "compilation_id": manifest.compilation_id,
            "gap_report": manifest.gap_report.model_dump(mode="json"),
            "persistence": persistence,
            "bundle": bundle,
        }, 0

    store_path: Path | str = database if not args.no_persist else ":memory:"
    with SQLiteStateStore(store_path, args.root) as store:
        result = ProjectIntakeService(store).bootstrap(
            manifest,
            apply=args.apply,
            confirm_existing=args.confirm_existing,
            actor_id=args.actor_id,
            correlation_id=args.correlation_id,
            persist=not args.no_persist,
        )
    return {
        "database": str(database),
        "compilation_id": manifest.compilation_id,
        "bundle": bundle,
        **result,
    }, 0 if result["ok"] else 1


def _load_json_model(path: Path | None, model: Any, *, argument: str) -> Any:
    if path is None:
        raise ConfigurationError(f"--{argument} is required")
    candidate = path.resolve() if path.is_absolute() else Path.cwd() / path
    if not candidate.exists() or not candidate.is_file():
        raise ConfigurationError(f"{argument} file does not exist: {path}")
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        return model.model_validate(payload)
    except Exception as error:
        raise ConfigurationError(f"invalid {argument} file: {error}") from error


def _load_context_candidates(path: Path | None) -> tuple[ContextCandidate, ...]:
    if path is None:
        raise ConfigurationError("--candidates is required")
    candidate = path.resolve() if path.is_absolute() else Path.cwd() / path
    if not candidate.exists() or not candidate.is_file():
        raise ConfigurationError(f"candidates file does not exist: {path}")
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("candidate payload must be a JSON array")
        return tuple(ContextCandidate.model_validate(item) for item in payload)
    except Exception as error:
        raise ConfigurationError(f"invalid candidates file: {error}") from error


def _run_context_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    artifact_root = args.artifact_root
    if artifact_root is not None and not artifact_root.is_absolute():
        artifact_root = (args.root / artifact_root).resolve()

    if args.action == "compile":
        envelope = _load_json_model(args.envelope, DelegationEnvelope, argument="envelope")
        candidates = _load_context_candidates(args.candidates)
        policy_path = args.policy or (args.root / "config" / "context_policy.json")
        policy = _load_json_model(policy_path, ContextPolicy, argument="policy")
        with ContextService(
            root=args.root, database=database, artifact_root=artifact_root
        ) as service:
            pack = service.compile(
                envelope,
                candidates,
                policy,
                provider_egress=ProviderEgress(args.provider_egress),
            )
            telemetry = service.compiler.telemetry(pack)
            return {
                "database": str(database),
                "pack": pack.model_dump(mode="json"),
                "telemetry": telemetry.model_dump(mode="json"),
            }, 0

    with ContextStore(database, args.root) as store:
        if args.action == "status":
            return {"database": str(database), "context": store.status()}, 0
        pack_id = str(_require_argument(args, "pack_id"))
        pack = store.get_pack(pack_id)
        if pack is None:
            return {
                "database": str(database),
                "error": "context_pack_not_found",
                "pack_id": pack_id,
            }, 1
        if args.action == "pack":
            return {"database": str(database), "pack": pack.model_dump(mode="json")}, 0
        compiler = ContextCompiler()
        if args.action == "telemetry":
            telemetry = compiler.telemetry(pack)
            return {"database": str(database), "telemetry": telemetry.model_dump(mode="json")}, 0
        if args.action == "review":
            review = compiler.reviewer_package(pack)
            return {"database": str(database), "review_package": review.model_dump(mode="json")}, 0

    worker_id = str(_require_argument(args, "worker_id"))
    receipt_status = ReceiptStatus(str(_require_argument(args, "receipt_status")))
    with ContextService(root=args.root, database=database, artifact_root=artifact_root) as service:
        receipt = service.receipt(
            pack_id=pack_id,
            worker_id=worker_id,
            status=receipt_status,
            omissions=tuple(args.omission),
            conflicts=tuple(args.conflict),
            requested=tuple(args.request_context),
        )
        return {"database": str(database), "receipt": receipt.model_dump(mode="json")}, 0


def _load_json_object(path: Path | None, *, argument: str) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        resolved = path.resolve()
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as error:
        raise ConfigurationError(f"invalid --{argument} JSON file: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigurationError(f"--{argument} must contain a JSON object")
    return payload


def _require_local_orchestration_apply(args: argparse.Namespace) -> None:
    if not args.apply or not args.approve:
        raise ConfigurationError(f"orchestration {args.action} requires both --apply and --approve")


def _run_orchestration_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.action == "simulate":
        scenario = str(_require_argument(args, "scenario"))
        result = simulate_orchestration_scenario(args.root, scenario)
        return {"simulation": result.model_dump(mode="json")}, 0 if result.passed else 1

    if args.action == "backend-status":
        adapters = (
            HatchetDurableAdapter(),
            DBOSFallbackAdapter(),
            TemporalFallbackAdapter(),
            MockDurableBackend(),
        )
        return {
            "backends": [item.capabilities().model_dump(mode="json") for item in adapters],
            "live_external_qualification_claimed": False,
        }, 0

    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    with OrchestrationStore(database, args.root) as store:
        runtime = LocalDurableRuntime(store)
        if args.action == "status":
            return {
                "database": str(database),
                "orchestration": store.status().model_dump(mode="json"),
            }, 0
        if args.action == "query":
            workflow_id = str(_require_argument(args, "workflow_id"))
            workflow = store.get_workflow(workflow_id)
            return {
                "database": str(database),
                "workflow": None if workflow is None else workflow.model_dump(mode="json"),
            }, 0 if workflow else 1

        _require_local_orchestration_apply(args)
        if args.action == "register":
            definition = _load_json_model(
                args.definition, WorkflowDefinition, argument="definition"
            )
            runtime.register_definition(definition)
            return {"database": str(database), "definition": definition.model_dump(mode="json")}, 0
        if args.action == "start":
            definition_id = str(_require_argument(args, "definition_id"))
            definition = store.get_definition(definition_id)
            if definition is None:
                raise ConfigurationError(f"unknown workflow definition: {definition_id}")
            backend = DurableBackendKind(args.backend)
            request = WorkflowStartRequest(
                definition_id=definition_id,
                idempotency_key=str(_require_argument(args, "idempotency_key")),
                input_payload=_load_json_object(args.input, argument="input"),
                backend=backend,
            )
            backends = {
                DurableBackendKind.HATCHET: HatchetDurableAdapter(),
                DurableBackendKind.DBOS: DBOSFallbackAdapter(),
                DurableBackendKind.TEMPORAL: TemporalFallbackAdapter(),
                DurableBackendKind.MOCK: MockDurableBackend(),
            }
            workflow = OrchestrationService(store, runtime, backends).start(
                request, workflow_name=args.workflow_name or definition.workflow_name
            )
            return {"database": str(database), "workflow": workflow.model_dump(mode="json")}, 0
        if args.action == "signal":
            workflow_id = str(_require_argument(args, "workflow_id"))
            signal_name = str(_require_argument(args, "signal_name"))
            idempotency_key = str(_require_argument(args, "idempotency_key"))
            signal = WorkflowSignal(
                signal_id=orchestration_identifier(
                    "signal", workflow_id, signal_name, idempotency_key
                ),
                workflow_id=workflow_id,
                signal_name=signal_name,
                idempotency_key=idempotency_key,
                payload=_load_json_object(args.payload, argument="payload"),
                observed_at_utc=datetime.now(UTC),
            )
            workflow = runtime.signal(signal)
            return {
                "database": str(database),
                "workflow": workflow.model_dump(mode="json"),
                "signal": signal.model_dump(mode="json"),
            }, 0
        if args.action == "checkpoint":
            workflow_id = str(_require_argument(args, "workflow_id"))
            checkpoint = runtime.checkpoint(
                workflow_id, _load_json_object(args.payload, argument="payload")
            )
            return {"database": str(database), "checkpoint": checkpoint.model_dump(mode="json")}, 0
        if args.action == "heartbeat":
            heartbeat = runtime.heartbeat(
                str(_require_argument(args, "worker_id")),
                fencing_epoch=int(_require_argument(args, "fencing_epoch")),
                ttl_seconds=args.ttl_seconds,
                active_workflow_ids=(str(args.workflow_id),) if args.workflow_id else (),
            )
            return {"database": str(database), "heartbeat": heartbeat.model_dump(mode="json")}, 0
        if args.action == "recover":
            manager = RecoveryManager(store, runtime)
            stale = manager.recover_stale_workers()
            unknown = manager.unknown_outcome_decisions()
            return {
                "database": str(database),
                "stale_worker_decisions": [item.model_dump(mode="json") for item in stale],
                "unknown_outcome_decisions": [item.model_dump(mode="json") for item in unknown],
            }, 0
        if args.action == "cancel":
            workflow_id = str(_require_argument(args, "workflow_id"))
            workflow = runtime.cancel(workflow_id)
            return {"database": str(database), "workflow": workflow.model_dump(mode="json")}, 0
        if args.action == "resume":
            workflow_id = str(_require_argument(args, "workflow_id"))
            workflow = runtime.resume(workflow_id)
            return {"database": str(database), "workflow": workflow.model_dump(mode="json")}, 0
        raise ConfigurationError(f"unsupported orchestration action: {args.action}")


def _require_local_budget_apply(args: argparse.Namespace) -> None:
    if not (args.apply and args.approve):
        raise ConfigurationError(f"budget {args.action} requires both --apply and --approve")


def _run_budget_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.action == "simulate":
        scenario = str(_require_argument(args, "scenario"))
        result = simulate_budget_scenario(args.root, scenario)
        return {"budget_simulation": result.model_dump(mode="json")}, 0
    if args.action == "preflight":
        target = Path(_require_argument(args, "path"))
        adapter = InfracostAdapter(allow_external_read=bool(args.allow_external_read))
        result = adapter.estimate(args.root, target)
        return {"infracost": result.model_dump(mode="json")}, 0 if result.available else 1

    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    policy_path = args.root / "config" / "budget_policy.json"
    policy = BudgetPolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))
    with BudgetStore(database, args.root) as store:
        governor = BudgetGovernor(store, policy)
        if args.action == "status":
            return {
                "database": str(database),
                "budget": store.status(args.project_id, cycle_id=args.cycle_id),
            }, 0
        if args.action == "metrics":
            return {
                "database": str(database),
                "metrics": governor.outcome_metrics(args.project_id).model_dump(mode="json"),
            }, 0
        if args.action == "admit":
            request = _load_json_model(args.request, BudgetAdmissionRequest, argument="request")
            decision = governor.admit(
                request,
                cycle_id=args.cycle_id,
                forecast_p90_microunits=args.forecast_p90_microunits,
                pace_ratio_milli=args.pace_ratio_milli,
            )
            return {
                "database": str(database),
                "decision": decision.model_dump(mode="json"),
            }, 0 if decision.admitted else 2
        if args.action == "forecast":
            result = governor.forecast(
                project_id=args.project_id,
                task_class=args.task_class,
                provider_id=args.provider_id,
                fallback_p50_microunits=max(0, args.p50_microunits),
                fallback_p90_microunits=args.p90_microunits,
                queued_task_count=max(0, args.queued_task_count),
                burn_rate_microunits_per_day=max(0, args.burn_rate_microunits_per_day),
                pace_ratio_milli=max(0, args.pace_ratio_milli),
                remaining_budget_microunits=args.remaining_budget_microunits,
            )
            return {"database": str(database), "forecast": result.model_dump(mode="json")}, 0
        if args.action == "impact":
            old_limit = _load_json_model(args.old_limit, BudgetLimit, argument="old_limit")
            new_limit = _load_json_model(args.limit, BudgetLimit, argument="limit")
            impact = governor.analyze_limit_change(old_limit, new_limit)
            return {"database": str(database), "impact": impact.model_dump(mode="json")}, 0

        _require_local_budget_apply(args)
        if args.action == "anomaly":
            expected = int(_require_argument(args, "expected_p90_microunits"))
            observed = int(_require_argument(args, "observed_microunits"))
            anomaly = governor.detect_anomaly(
                project_id=args.project_id,
                expected_p90_microunits=max(0, expected),
                observed_microunits=max(0, observed),
                provider_id=args.provider_id,
            )
            return {
                "database": str(database),
                "anomaly": anomaly.model_dump(mode="json"),
            }, 0 if not anomaly.block_new_paid_work else 2
        if args.action == "limit":
            limit = _load_json_model(args.limit, BudgetLimit, argument="limit")
            governor.configure_limit(limit)
            return {"database": str(database), "limit": limit.model_dump(mode="json")}, 0
        if args.action == "quota":
            quota = _load_json_model(args.quota, QuotaLimit, argument="quota")
            governor.configure_quota(quota)
            return {"database": str(database), "quota": quota.model_dump(mode="json")}, 0
        if args.action == "reserve":
            request = _load_json_model(args.request, BudgetAdmissionRequest, argument="request")
            decision = _load_json_model(args.decision, BudgetAdmissionDecision, argument="decision")
            lease = governor.reserve(
                request,
                decision,
                cycle_id=args.cycle_id,
                idempotency_key=str(_require_argument(args, "idempotency_key")),
            )
            return {"database": str(database), "lease": lease.model_dump(mode="json")}, 0
        if args.action == "settle":
            lease_id = str(_require_argument(args, "lease_id"))
            entry = _load_json_model(args.entry, BudgetLedgerEntry, argument="entry")
            lease = governor.settle(lease_id, entry)
            return {"database": str(database), "lease": lease.model_dump(mode="json")}, 0
        if args.action == "unknown":
            lease = governor.mark_unknown_outcome(str(_require_argument(args, "lease_id")))
            return {"database": str(database), "lease": lease.model_dump(mode="json")}, 0
        if args.action == "reconcile-no-effect":
            lease = governor.reconcile_unknown(
                str(_require_argument(args, "lease_id")), remote_effect_occurred=False
            )
            return {"database": str(database), "lease": lease.model_dump(mode="json")}, 0
        raise ConfigurationError(f"unsupported budget action: {args.action}")


def _require_assurance_record_apply(args: argparse.Namespace) -> None:
    if args.record and not (args.apply and args.approve):
        raise ConfigurationError("assurance --record requires both --apply and --approve")


def _assurance_database(args: argparse.Namespace) -> Path:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    try:
        SQLiteMigrationRunner(conn, args.root).apply_all()
    finally:
        conn.close()
    return database


def _run_assurance_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.action == "simulate":
        scenario = str(_require_argument(args, "scenario"))
        result = simulate_assurance_scenario(scenario)
        return {"assurance_simulation": result.model_dump(mode="json")}, 0 if result.passed else 1

    if args.action == "candidate":
        payload = _load_json_object(args.input, argument="input")
        result = assess_candidate_completion(**payload)
        return {
            "candidate_completion": result.model_dump(mode="json")
        }, 0 if result.state.value == "READY_FOR_COMPLETION_GATE" else 1

    if args.action == "delivery-gate":
        base_ref = str(_require_argument(args, "base_ref"))
        delivery_policy = load_delivery_policy(args.root)
        delivery_decision = evaluate_delivery_gate(
            args.root,
            base_ref=base_ref,
            head_ref=str(args.head_ref),
            minimum_reconciliation_batch_items=int(
                delivery_policy["minimum_reconciliation_batch_items"]
            ),
            maximum_noncritical_administrative_ratio_milli=int(
                delivery_policy["maximum_noncritical_administrative_ratio_milli"]
            ),
        )
        return {
            "delivery_gate": delivery_decision.model_dump(mode="json"),
            "policy": delivery_policy,
        }, 0 if delivery_decision.state.value == "PASS" else 1

    database = _assurance_database(args)
    store = AssuranceStore(database)
    if args.action == "status":
        return {"database": str(database), "assurance": store.status(args.project_id)}, 0

    _require_assurance_record_apply(args)
    if args.action == "compile":
        plan = compile_repository_plan(args.root, args.project_id)
        if args.record:
            store.save_plan(plan)
        return {
            "database": str(database),
            "mode": "RECORDED" if args.record else "DRY_RUN",
            "verification_plan": plan.model_dump(mode="json"),
        }, 0

    if args.action == "completion-gate":
        facts = build_repository_gate_facts(args.root, args.project_id)
        decision = evaluate_completion_gate(facts)
        if args.record:
            store.save_gate(decision)
        return {
            "database": str(database),
            "mode": "RECORDED" if args.record else "DRY_RUN",
            "facts": facts.model_dump(mode="json"),
            "completion_gate": decision.model_dump(mode="json"),
        }, 0 if decision.final_complete else 1

    if args.action == "loop-guard":
        payload = _load_json_object(args.input, argument="input")
        observations = tuple(
            AttemptObservation.model_validate(item) for item in payload.get("observations", ())
        )
        assurance_policy = AssurancePolicy.model_validate_json(
            (args.root / "config" / "assurance_policy.json").read_text(encoding="utf-8")
        )
        budget_payload = {
            "max_attempts": assurance_policy.loop_max_attempts,
            "max_same_failure": assurance_policy.loop_max_same_failure,
            "max_unchanged_outputs": assurance_policy.loop_max_unchanged_outputs,
            "max_progressless_cycles": assurance_policy.loop_max_progressless_cycles,
            "max_noncritical_administrative_ratio_milli": assurance_policy.delivery_progress.maximum_noncritical_administrative_ratio_milli,
            **payload.get("budget", {}),
        }
        budget = AttemptBudget.model_validate(budget_payload)
        decision = evaluate_loop(observations, budget)
        if args.record:
            store.save_loop(args.project_id, decision)
        return {
            "database": str(database),
            "mode": "RECORDED" if args.record else "DRY_RUN",
            "loop_guard": decision.model_dump(mode="json"),
        }, 0 if decision.disposition.value == "CONTINUE" else 1

    if args.action == "scope-change":
        contract = _load_json_model(args.scope, ScopeContract, argument="scope")
        decision = evaluate_scope_change(
            contract,
            requested_behavior=tuple(args.requested_behavior),
            requested_paths=tuple(args.requested_path),
        )
        if args.record:
            store.save_scope(args.project_id, contract)
            store.save_scope_change(args.project_id, decision)
        return {
            "database": str(database),
            "mode": "RECORDED" if args.record else "DRY_RUN",
            "scope_change": decision.model_dump(mode="json"),
        }, 0 if decision.disposition.value == "WITHIN_FROZEN_SCOPE" else 1

    raise ConfigurationError(f"unsupported assurance action: {args.action}")


def _verification_database(args: argparse.Namespace) -> Path:
    configuration = _load_configuration(args)
    database = _state_database_path(args, configuration)
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    try:
        SQLiteMigrationRunner(conn, args.root).apply_all()
    finally:
        conn.close()
    return database


def _require_verification_apply(args: argparse.Namespace, action: str) -> None:
    if not (args.apply and args.approve):
        raise ConfigurationError(f"verification {action} requires both --apply and --approve")


def _security_database(args: argparse.Namespace) -> Path | str:
    if args.database is not None:
        return (
            args.database
            if str(args.database) == ":memory:"
            else (
                args.database if args.database.is_absolute() else args.root / args.database
            ).resolve()
        )
    return (args.root / ".local/state/security.sqlite3").resolve()


def _run_security_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.action == "simulate":
        result = simulate_security(str(_require_argument(args, "scenario")))
        return {"security_simulation": result}, 0
    if args.action == "tools":
        tools = {
            "trivy": TrivyAdapter().available(),
            "opa": OpaAdapter().available(),
            "conftest": ConftestAdapter().available(),
            "scorecard": ScorecardAdapter().available(),
            "sops": SopsAdapter().available(),
            "age": AgeAdapter().available(),
            "gitleaks": GitleaksAdapter().available(),
            "osv-scanner": OsvScannerAdapter().available(),
            "cosign": CosignVerifyAdapter().available(),
            "zizmor": ZizmorAdapter().available(),
        }
        return {
            "project_id": args.project_id,
            "security_tools": tools,
            "live_external_claim": False,
        }, 0
    if args.action == "root-trust":
        value = RootOfTrust.model_validate(
            json.loads((args.root / "config/root_of_trust.json").read_text(encoding="utf-8"))
        )
        return {"root_of_trust": value.model_dump(mode="json")}, 0
    if args.action == "sbom":
        sbom = build_repository_sbom(args.root, project_id=args.project_id)
        return {"sbom": sbom.model_dump(mode="json")}, 0
    if args.action == "supply-chain":
        gate, sbom = evaluate_supply_chain(args.root)
        return {
            "supply_chain_gate": gate.model_dump(mode="json"),
            "sbom_id": sbom.sbom_id if sbom else None,
        }, 0 if gate.state.value == "PASS" else 1
    if args.action == "self-modification":
        assessment = assess_self_modification(tuple(args.changed_path))
        return {"self_modification": assessment.model_dump(mode="json")}, 0
    database = _security_database(args)
    if args.action == "status":
        with SecurityStore(database, args.root) as store:
            return {"database": str(database), "security": store.status()}, 0
    if args.action == "record-identity":
        if not (args.apply and args.approve):
            raise ConfigurationError("security record-identity requires --apply --approve")
        path = _require_argument(args, "input")
        value = SecurityIdentity.model_validate(json.loads(path.read_text(encoding="utf-8")))
        with SecurityStore(database, args.root) as store:
            store.save_identity(value)
        return {"database": str(database), "recorded_identity_id": value.identity_id}, 0
    raise ConfigurationError(f"unsupported security action: {args.action}")


def _resilience_database(args: argparse.Namespace) -> Path | str:
    if args.database is not None:
        return (
            args.database
            if str(args.database) == ":memory:"
            else (
                args.database if args.database.is_absolute() else args.root / args.database
            ).resolve()
        )
    return (args.root / ".local/state/resilience.sqlite3").resolve()


def _run_resilience_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.action == "simulate":
        result = simulate_resilience_scenario(args.root, str(_require_argument(args, "scenario")))
        return {"resilience_simulation": result}, 0 if result["passed"] else 1
    if args.action == "tools":
        return {
            "resilience_tools": resilience_activation_snapshot(),
            "live_external_claim": False,
        }, 0
    if args.action == "local-runtime":
        gateway = LocalModelGateway(load_local_runtimes(args.root))
        required = tuple(args.capability or ["summarization"])
        runtime = gateway.select(required)
        return {
            "required_capabilities": list(required),
            "selected": runtime.model_dump(mode="json") if runtime else None,
            "validation_errors": gateway.validate(),
            "live_invocation_performed": False,
        }, 0 if runtime else 1
    if args.action in {"backup-plan", "restore-plan"}:
        planner = BackupPlanner(load_recovery_objectives(args.root))
        domain = str(_require_argument(args, "domain"))
        if args.action == "backup-plan":
            return {
                "backup_plan": planner.plan_backup(
                    domain=domain,
                    source=str(_require_argument(args, "source")),
                    repository=str(args.repository),
                )
            }, 0
        return {
            "restore_plan": planner.plan_restore(
                domain=domain,
                repository=str(args.repository),
                isolated_target=str(_require_argument(args, "target")),
            )
        }, 0
    if args.action == "aws-plan":
        return {"aws_plan": aws_safety_plan(args.root)}, 0
    if args.action == "status":
        database = _resilience_database(args)
        with ResilienceStore(database, args.root) as store:
            return {
                "database": str(database),
                "resilience": store.status(),
                "objectives": [
                    x.model_dump(mode="json") for x in load_recovery_objectives(args.root)
                ],
            }, 0
    raise ConfigurationError(f"unsupported resilience action: {args.action}")


def _run_verification_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    policy = load_verification_policy(args.root)
    if args.action == "simulate":
        scenario = str(_require_argument(args, "scenario"))
        result = simulate_verification_scenario(args.root, scenario)
        return {"verification_simulation": result}, 0 if result["passed"] else 1

    if args.action == "tools":
        values = verification_activation_snapshot(args.root)
        return {
            "project_id": args.project_id,
            "verification_tools": [item.model_dump(mode="json") for item in values],
        }, 0

    if args.action == "plan":
        specs = verification_default_check_specs()
        return {
            "project_id": args.project_id,
            "profile": policy.profile,
            "required_categories": [item.value for item in policy.required_categories],
            "checks": [item.model_dump(mode="json") for item in specs],
        }, 0

    if args.action == "impact":
        if not args.changed_path and not args.dependency_path and not args.requirement_id:
            raise ConfigurationError(
                "verification impact requires --changed-path, --dependency-path, or --requirement-id"
            )
        impact = verification_derive_test_impact(
            args.changed_path,
            dependency_paths=args.dependency_path,
            requirement_ids=args.requirement_id,
            risk=args.risk,
            acceptance_methods=args.acceptance_method,
            profile_categories=policy.required_categories,
        )
        return {"project_id": args.project_id, "test_impact": impact.model_dump(mode="json")}, 0

    if args.action == "journeys":
        definitions = verification_golden_journey_definitions()
        results = verification_run_golden_journeys(args.root)
        passed = all(item.state.value == "PASS" for item in results)
        return {
            "project_id": args.project_id,
            "journeys": [item.model_dump(mode="json") for item in definitions],
            "results": [item.model_dump(mode="json") for item in results],
        }, 0 if passed else 1

    if args.action == "browser":
        _require_verification_apply(args, "browser")
        chromium = verification_find_chromium(policy.system_chromium_candidates)
        if chromium is None:
            return {
                "project_id": args.project_id,
                "state": "BLOCKED",
                "reason": "Chromium executable unavailable",
            }, 2
        issues = json.loads(
            (args.root / "jira/indexes/issues_by_id.json").read_text(encoding="utf-8")
        )
        manifest = json.loads((args.root / "PROJECT_MANIFEST.json").read_text(encoding="utf-8"))
        coverage = json.loads(
            (args.root / "plans/_traceability/coverage_report.json").read_text(encoding="utf-8")
        )
        report_path = verification_render_report(
            args.root,
            summary={
                "repository_files": manifest.get("file_count"),
                "repository_aggregate_sha256": manifest.get("aggregate_sha256"),
                "requirements": coverage.get("requirement_count"),
                "unexplained_traceability_gaps": coverage.get(
                    "unexplained_gap_count", coverage.get("gap_count")
                ),
                "jira_issues": len(issues),
                "completion_authority": "Execution Assurance Completion Gate",
            },
        )
        browser, accessibility = verification_verify_report(
            args.root, report_path, chromium_path=chromium, viewports=policy.screenshot_viewports
        )
        passed = all(item.passed for item in browser) and accessibility.passed
        return {
            "project_id": args.project_id,
            "report": report_path.relative_to(args.root).as_posix(),
            "browser": [item.model_dump(mode="json") for item in browser],
            "accessibility": accessibility.model_dump(mode="json"),
        }, 0 if passed else 1

    database = _verification_database(args)
    if args.action == "status":
        with VerificationStore(database, args.root) as store:
            return {"database": str(database), "verification": store.status(args.project_id)}, 0

    if args.action == "run":
        _require_verification_apply(args, "run")
        harness = VerificationHarness(args.root, policy)
        run, details = harness.run()
        activations = details.get("activations") or ()
        journeys = details.get("golden_journeys") or ()
        with VerificationStore(database, args.root) as store:
            for activation in activations:
                store.save_activation(args.project_id, activation)
            for journey in journeys:
                store.save_journey(args.project_id, journey)
            store.save_run(run)
        return {
            "database": str(database),
            "verification_run": run.model_dump(mode="json"),
            "tool_activations": [item.model_dump(mode="json") for item in activations],
        }, 0 if run.final_state.value == "PASS" else 1

    raise ConfigurationError(f"unsupported verification action: {args.action}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            report = run_bootstrap(
                args.root,
                _load_configuration(args),
                prepare=False,
                validate_repository=False,
            )
            _write_json_output(report.as_dict(), None)
            return 0 if report.ok else 1
        if args.command == "config":
            configuration = _load_configuration(args)
            _write_json_output(configuration.as_dict(), args.json_output)
            return 0
        if args.command == "bootstrap":
            report = run_bootstrap(
                args.root,
                _load_configuration(args),
                prepare=args.prepare,
                validate_repository=not args.skip_repository_validation,
            )
            _write_json_output(report.as_dict(), args.json_output)
            return 0 if report.ok else 1
        if args.command == "smoke":
            report = run_foundation_smoke(args.root, _load_configuration(args))
            _write_json_output(report.as_dict(), args.json_output)
            return 0 if report.ok else 1
        if args.command == "schemas":
            if args.action == "write":
                _write_json_output({"written": write_schemas(args.root)}, None)
                return 0
            errors = validate_schemas(args.root)
            _write_json_output({"ok": not errors, "errors": errors}, None)
            return 0 if not errors else 1
        if args.command == "dependencies":
            if args.action == "lock":
                result = build_environment_lock(args.root)
                _write_json_output(result, args.json_output)
                return 0
            if args.action == "validate":
                errors = validate_dependency_lock(args.root, verify_installed=args.verify_installed)
                _write_json_output({"ok": not errors, "errors": errors}, args.json_output)
                return 0 if not errors else 1
            if args.action == "snapshot":
                result = write_dependency_snapshot(args.root)
                _write_json_output(result, args.json_output)
                return 0
            result = {
                "schema_version": "1.0.0",
                "snapshot": dependency_snapshot(args.root),
                "dependencies": [item.as_dict() for item in dependency_status(args.root)],
                "errors": validate_dependency_lock(args.root),
            }
            result["ok"] = not result["errors"]
            _write_json_output(result, args.json_output)
            return 0 if result["ok"] else 1
        if args.command == "quality":
            report = run_quality(args.root, strict_tools=args.strict_tools, coverage=args.coverage)
            if args.json_output:
                write_quality_report(report, args.json_output)
            _write_json_output(report.as_dict(), None)
            return 0 if report.ok else 1
        if args.command == "validate":
            report = RepositoryValidator(args.root).validate()
            print(report.render())
            if args.json_output:
                _write_json_output(report.as_dict(), args.json_output)
            return 0 if report.ok else 1
        if args.command == "manifest":
            manifest = write_manifest(args.root)
            _write_json_output(
                {
                    "aggregate_sha256": manifest["aggregate_sha256"],
                    "file_count": manifest["file_count"],
                    "total_bytes": manifest["total_bytes"],
                },
                None,
            )
            return 0
        if args.command == "map":
            result = write_repository_map(args.root)
            _write_json_output(
                {"by_top_level": result["by_top_level"], "file_count": result["file_count"]},
                None,
            )
            return 0
        if args.command == "line-plans":
            result = generate_line_numbered_plans(args.root)
            _write_json_output({"section_count": len(result)}, None)
            return 0
        if args.command == "coverage":
            rebuild_traceability_exports(args.root)
            result = write_coverage_artifacts(args.root)
            _write_json_output(result, None)
            return 0 if result["unexplained_gap_count"] == 0 else 1
        if args.command == "requirements":
            if args.id:
                item = requirement_index(args.root).get(args.id)
                if item is None:
                    _write_json_output(
                        {"error": "requirement_not_found", "requirement_id": args.id}, None
                    )
                    return 1
                _write_json_output(item, None)
                return 0
            rows = find_requirements(
                args.root,
                domain=args.domain,
                implementation_state=args.state,
                disposition=args.disposition,
                priority=args.priority,
                source_id=args.source,
                text=args.text,
            )
            _write_json_output(summarize_requirements(rows) if args.summary else rows, None)
            return 0
        if args.command == "jira-rebuild":
            result = rebuild_jira_indexes(args.root)
            _write_json_output(result["status"], None)
            return 0
        if args.command == "requirement-views":
            _write_json_output(write_requirement_views(args.root), None)
            return 0
        if args.command == "architecture":
            if args.write_views:
                _write_json_output(write_architecture_views(args.root), None)
                return 0
            if args.stack:
                _write_json_output(load_technology_stack(args.root), None)
                return 0
            if args.summary:
                _write_json_output(summarize_architecture(args.root), None)
                return 0
            rows = find_components(
                args.root,
                component_id=args.component,
                layer=args.layer,
                implementation_state=args.state,
                text=args.text,
            )
            _write_json_output(rows, None)
            return 0 if rows or not args.component else 1
        if args.command == "state":
            result, code = _run_state_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "trace-store":
            result, code = _run_trace_store_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "intake":
            result, code = _run_intake_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "jira":
            result, code = _run_jira_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "repository":
            result, code = _run_repository_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "github":
            result, code = _run_github_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "control":
            result, code = _run_control_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "scheduler":
            result, code = _run_scheduler_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "takeover":
            result, code = _run_takeover_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "agent-router":
            result, code = _run_agent_router_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "context":
            result, code = _run_context_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "orchestration":
            result, code = _run_orchestration_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "budget":
            result, code = _run_budget_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "assurance":
            result, code = _run_assurance_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "verification":
            result, code = _run_verification_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "security":
            result, code = _run_security_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "resilience":
            result, code = _run_resilience_command(args)
            _write_json_output(result, args.json_output)
            return code
        if args.command == "upstream":
            if args.write_views:
                _write_json_output(write_upstream_views(args.root), None)
                return 0
            if args.summary:
                _write_json_output(summarize_upstreams(args.root), None)
                return 0
            if args.convergence:
                result = load_p0_convergence(args.root)
                _write_json_output(result, None)
                return 0 if result.get("status") == "PASS" else 1
            rows = find_upstreams(
                args.root,
                upstream_id=args.id,
                repository=args.repository,
                disposition=args.disposition,
                inspection_state=args.inspection_state,
                subsystem=args.subsystem,
                text=args.text,
            )
            _write_json_output(rows, None)
            return 0 if rows or not (args.id or args.repository) else 1
        if args.command == "archive":
            output = create_archive(args.root, args.output)
            report = verify_archive(output, args.root.name)
            _write_json_output(report.as_dict(), None)
            return 0 if report.ok else 1
        if args.command == "verify-archive":
            report = verify_archive(
                args.archive,
                args.expected_root,
                enforce_repository_policy=not args.source_bearing,
            )
            _write_json_output(report.as_dict(), None)
            return 0 if report.ok else 1
    except (
        BootstrapError,
        ControlGraphError,
        ConfigurationError,
        DiscoveryError,
        FileExistsError,
        PersistenceError,
        JiraStewardError,
        GitHubStewardError,
        LocalGitError,
        SecretResolutionError,
        ValueError,
    ) as error:
        error_name = (
            "configuration_invalid"
            if isinstance(error, ConfigurationError)
            else type(error).__name__
        )
        _write_json_output(
            {
                "ok": False,
                "error": error_name,
                "message": str(error),
            },
            getattr(args, "json_output", None),
        )
        return 2
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
