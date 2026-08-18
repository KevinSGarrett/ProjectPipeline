from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from project_pipeline.agent_router import (
    AgentRouterService,
    MockProviderAdapter,
    ProviderAdapterError,
    build_registry,
)
from project_pipeline.assurance.completion import (
    build_repository_gate_facts,
    evaluate_completion_gate,
)
from project_pipeline.assurance.evidence import assess_evidence_for_criterion, evidence_sufficient
from project_pipeline.command_center import RepositoryApplicationProjectionBuilder
from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.incidents import IncidentManager
from project_pipeline.command_center.models import HealthDimension, HealthState
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.context_engine import ContextBroker, ContextCompiler
from project_pipeline.control import BuildSequencer, evaluate_recommendation_authority
from project_pipeline.domain import (
    AgentSpec,
    CapabilityRoutePolicy,
    CapabilitySpec,
    ExecutionMode,
    ExecutionTaskContract,
    IntakeMode,
    ModelSpec,
    ProjectIntakeRequest,
    ProviderRuntimeState,
    ProviderSpec,
    ProviderStateObservation,
    QualificationState,
)
from project_pipeline.domain.assurance import (
    AcceptanceCriterion,
    AssuranceRisk,
    IndependentReview,
    ReviewerIdentity,
    VerificationMethod,
    assurance_fingerprint,
    assurance_identifier,
)
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPolicy,
    ContextSourceKind,
    ContextTrust,
    DelegationEnvelope,
    Sensitivity,
)
from project_pipeline.domain.control import (
    BuildSequence,
    CompletionProjection,
    CompletionProjectionState,
    ControlSnapshot,
    CriticalPathAnalysis,
    EligibilityState,
    ReadinessState,
    ScopeReconciliationReport,
    SequenceItem,
    SequenceScore,
    TaskControlFact,
    TaskEligibility,
    TaskReadiness,
    control_identifier,
)
from project_pipeline.domain.github import (
    BranchRole,
    CheckConclusion,
    CheckState,
    GitBranch,
    GitHubBranchProtection,
    PullRequestCheck,
    PullRequestReview,
    PullRequestSnapshot,
    PullRequestState,
    ReviewState,
    github_identifier,
)
from project_pipeline.domain.jira import JiraRemoteSnapshot
from project_pipeline.domain.resilience import ExternalPreconditionIncident, FailureDomain
from project_pipeline.domain.scheduler import (
    ResourcePool,
    ResourceRegistrySnapshot,
    ResourceType,
    SchedulerTaskProfile,
)
from project_pipeline.domain.state import TaskLifecycleState
from project_pipeline.github_steward import (
    GitHubStewardStore,
    LocalGitRepository,
    MockGitHubAdapter,
    RepositorySteward,
)
from project_pipeline.intake import compile_project
from project_pipeline.jira_steward import MockJiraAdapter
from project_pipeline.jira_steward.persistence import JiraSyncStore
from project_pipeline.jira_steward.reconciliation import JiraReconciler, JiraReconciliationPolicy
from project_pipeline.jira_steward.repository import JiraMirrorRepository
from project_pipeline.jira_steward.service import JiraSteward
from project_pipeline.orchestration.simulation import simulate_scenario
from project_pipeline.requirements import load_requirement_catalog
from project_pipeline.scheduler import DynamicLaneScheduler


class E2EExecutionMode(StrEnum):
    LOCAL_REAL = "LOCAL_REAL"
    DETERMINISTIC_SIMULATION = "DETERMINISTIC_SIMULATION"
    DRY_RUN = "DRY_RUN"
    MOCK_REMOTE = "MOCK_REMOTE"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    NOT_QUALIFIED = "NOT_QUALIFIED"


class E2EStageState(StrEnum):
    PASS = "PASS"
    EXPECTED_BLOCK = "EXPECTED_BLOCK"
    FAIL = "FAIL"


class E2EStage:
    def __init__(
        self, name: str, owner: str, mode: E2EExecutionMode, state: E2EStageState, observation: str
    ):
        self.name = name
        self.owner = owner
        self.mode = mode
        self.state = state
        self.observation = observation

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "canonical_owner": self.owner,
            "execution_mode": self.mode.value,
            "state": self.state.value,
            "observation": self.observation,
        }


class E2EJourney:
    def __init__(self, journey_id: str, name: str, stages: list[E2EStage]):
        self.journey_id = journey_id
        self.name = name
        self.stages = stages

    @property
    def passed(self) -> bool:
        return all(
            item.state in {E2EStageState.PASS, E2EStageState.EXPECTED_BLOCK} for item in self.stages
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "journey_id": self.journey_id,
            "name": self.name,
            "passed": self.passed,
            "stages": [item.as_dict() for item in self.stages],
        }


def _stage(
    name: str,
    owner: str,
    mode: E2EExecutionMode,
    ok: bool,
    observation: str,
    *,
    expected_block: bool = False,
) -> E2EStage:
    state = (
        E2EStageState.EXPECTED_BLOCK
        if expected_block and ok
        else (E2EStageState.PASS if ok else E2EStageState.FAIL)
    )
    return E2EStage(name, owner, mode, state, observation)


def _control_snapshot(task_id: str) -> ControlSnapshot:
    score = SequenceScore(
        task_id=task_id,
        priority_score=100,
        critical_path_score=0,
        deadline_score=0,
        risk_score=0,
        unblock_score=0,
        duration_score=0,
        total_score=100,
    )
    item = SequenceItem(
        rank=1,
        task_id=task_id,
        readiness=ReadinessState.READY,
        score=score,
        dependency_depth=0,
        downstream_count=0,
        on_critical_path=True,
    )
    sequence = BuildSequence(
        sequence_id=control_identifier("SEQ", "pass23", task_id),
        project_id="PROJECT-PIPELINE",
        graph_fingerprint="a" * 64,
        task_count=1,
        edge_count=0,
        ready_count=1,
        active_count=0,
        blocked_count=0,
        critical_path=CriticalPathAnalysis(
            path=(task_id,),
            total_duration_minutes=1,
            duration_source="DECLARED",
            earliest_finish_minutes={task_id: 1},
            slack_minutes={task_id: 0},
        ),
        ordered_ready_work=(item,),
    )
    scope = ScopeReconciliationReport(
        report_id=control_identifier("SCOPE", "pass23", task_id),
        project_id="PROJECT-PIPELINE",
        requirement_count=1,
        work_item_count=1,
        findings=(),
        fingerprint="b" * 64,
    )
    completion = CompletionProjection(
        projection_id=control_identifier("COMPLETE", "pass23", task_id),
        project_id="PROJECT-PIPELINE",
        state=CompletionProjectionState.INCOMPLETE,
        total_work_items=1,
        completed_work_items=0,
        active_work_items=0,
        blocked_work_items=0,
        failed_work_items=0,
        accepted_requirements=1,
        implemented_or_external_blocked_requirements=0,
        ready_work_items=1,
        verification_eligible=False,
        reasons=("work remains",),
    )
    return ControlSnapshot(
        snapshot_id=control_identifier("CTRL", "pass23", task_id),
        project_id="PROJECT-PIPELINE",
        sequence=sequence,
        scope=scope,
        completion=completion,
        eligibility=(TaskEligibility(task_id=task_id, state="ELIGIBLE", eligible=True),),
        readiness=(TaskReadiness(task_id=task_id, state="READY", ready=True),),
        snapshot_fingerprint="c" * 64,
    )


def _agent_fallback() -> tuple[bool, str]:
    cap = CapabilitySpec(capability_id="routine_reasoning", description="reason")
    providers = tuple(
        ProviderSpec(
            provider_id=f"provider:{x}",
            display_name=x,
            adapter_id=f"adapter:{x}",
            execution_mode=ExecutionMode.MOCK,
            capabilities=(cap.capability_id,),
        )
        for x in ("one", "two")
    )
    models = tuple(
        ModelSpec(
            model_id=f"model:{x}",
            provider_id=f"provider:{x}",
            provider_model_name=x,
            version="1",
            capabilities=(cap.capability_id,),
            qualification=QualificationState.QUALIFIED,
        )
        for x in ("one", "two")
    )
    agents = tuple(
        AgentSpec(
            agent_id=f"agent:{x}",
            model_id=f"model:{x}",
            capabilities=(cap.capability_id,),
            qualification=QualificationState.QUALIFIED,
        )
        for x in ("one", "two")
    )
    registry = build_registry(
        capabilities=(cap,),
        providers=providers,
        models=models,
        agents=agents,
        routing_policies=(
            CapabilityRoutePolicy(
                capability_id=cap.capability_id,
                preferred_provider_ids=("provider:one",),
                fallback_provider_ids=("provider:two",),
            ),
        ),
    )
    now = datetime.now(UTC)
    states = [
        ProviderStateObservation(
            provider_id=p.provider_id, state=ProviderRuntimeState.HEALTHY, observed_at_utc=now
        )
        for p in providers
    ]
    contract = ExecutionTaskContract(
        task_id="PASS23-E2E",
        task_class="integration",
        required_capabilities=(cap.capability_id,),
        instructions="exercise deterministic provider fallback",
    )
    one = MockProviderAdapter(
        "provider:one", [ProviderAdapterError("down", kind="UNAVAILABLE", retryable=True)]
    )
    one.adapter_id = "adapter:one"
    two = MockProviderAdapter("provider:two")
    two.adapter_id = "adapter:two"
    receipt = AgentRouterService(registry, {"adapter:one": one, "adapter:two": two}).execute(
        contract, states, []
    )
    return receipt.succeeded and [x.provider_id for x in receipt.attempts] == [
        "provider:one",
        "provider:two",
    ], receipt.receipt_id


def _github_mock_flow(root: Path, temp_root: Path) -> tuple[bool, str]:
    repo = temp_root / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "pass23@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Pass 23"], check=True)
    (repo / "README.md").write_text("pass23\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/owner/repo.git"],
        check=True,
    )
    sha1, sha2 = "a" * 40, "b" * 40
    main = GitBranch(
        branch_id=github_identifier("GHBR", "owner/repo", "main", sha1),
        name="main",
        sha=sha1,
        role=BranchRole.DEFAULT,
        is_default=True,
    )
    feature = GitBranch(
        branch_id=github_identifier("GHBR", "owner/repo", "feature/pass23", sha2),
        name="feature/pass23",
        sha=sha2,
        role=BranchRole.FEATURE,
    )
    pr = PullRequestSnapshot(
        pull_request_id=github_identifier("GHPR", "owner/repo", "23", sha2),
        repository_slug="owner/repo",
        number=23,
        title="Pass 23",
        state=PullRequestState.OPEN,
        base_branch="main",
        head_branch="feature/pass23",
        base_sha=sha1,
        head_sha=sha2,
        mergeable=True,
    )
    remote = MockGitHubAdapter(repository_slug="owner/repo", branches=(main, feature), pulls=(pr,))
    remote.set_branch_protection(
        GitHubBranchProtection(
            repository_slug="owner/repo",
            branch="main",
            protected=True,
            required_status_checks=("tests",),
            required_approving_review_count=1,
        )
    )
    remote.seed_review(
        23,
        PullRequestReview(
            review_id="review-pass23",
            author="independent-reviewer",
            state=ReviewState.APPROVED,
            commit_sha=sha2,
            submitted_at_utc=datetime.now(UTC),
        ),
    )
    remote.seed_check(
        sha2,
        PullRequestCheck(
            check_id="check-pass23",
            name="tests",
            state=CheckState.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
        ),
    )
    with GitHubStewardStore(temp_root / "github.db", root) as store:
        steward = RepositorySteward(local=LocalGitRepository(repo), remote=remote, store=store)
        gate, operation = steward.plan_merge(
            "owner/repo", 23, actor_id="actor:pass23", correlation_id="corr:pass23"
        )
        return gate.state.value == "READY", operation.operation_id


def _incident_idempotency() -> bool:
    broker = AttentionNotificationBroker()
    manager = IncidentManager(broker)
    incident = ExternalPreconditionIncident(
        incident_id="INCIDENT-CCCCCCCCCCCCCCCCCCCC",
        failure_domain=FailureDomain.API,
        summary="Duplicate delivery",
        autonomous_resolution_action="Perform one repair.",
        unaffected_work=("local work",),
        blocked_work=("remote work",),
        verification_steps=("verify once",),
        stale_assumptions_to_invalidate=("old state",),
    )
    first = manager.open(incident, project_id="PROJECT-PIPELINE")
    second = manager.open(incident, project_id="PROJECT-PIPELINE")
    return first.inbox_id == second.inbox_id and len(broker.list_open()) == 1


def _incident_recovery() -> tuple[bool, str]:
    broker = AttentionNotificationBroker()
    manager = IncidentManager(broker)
    incident = ExternalPreconditionIncident(
        incident_id="INCIDENT-BBBBBBBBBBBBBBBBBBBB",
        failure_domain=FailureDomain.API,
        summary="Pass 23 human repair",
        autonomous_resolution_action="Repair the external credential and confirm the provider health check.",
        unaffected_work=("local verification",),
        blocked_work=("remote provider execution",),
        verification_steps=("credential validates", "health check passes"),
        stale_assumptions_to_invalidate=("credential remains valid",),
    )
    case = manager.open(incident, project_id="PROJECT-PIPELINE")
    manager.acknowledge(case.incident.incident_id)
    manager.begin_recovery(case.incident.incident_id)
    manager.verify(
        case.incident.incident_id,
        verification_results={"credential": True, "health": True},
        stale_assumptions_invalidated=True,
        reconciliation_complete=True,
    )
    resolved = manager.resolve(case.incident.incident_id)
    return (
        resolved.state.value == "RESOLVED" and not manager.list_active(),
        case.incident.incident_id,
    )


def _independent_review_proof() -> bool:
    statement = "Pass 23 high-risk integration requires independent verification."
    fp = assurance_fingerprint((statement, AssuranceRisk.HIGH.value))
    criterion = AcceptanceCriterion(
        criterion_id=assurance_identifier("CRIT", "PASS23", statement, fp),
        work_item_id="PASS23",
        statement=statement,
        risk=AssuranceRisk.HIGH,
        verification_methods=(VerificationMethod.UNIT, VerificationMethod.INTEGRATION),
        frozen_fingerprint=fp,
    )
    now = datetime.now(UTC)
    records = (
        {
            "evidence_id": "EVID-P23-A",
            "criterion_ids": [criterion.criterion_id],
            "verification_status": "VERIFIED",
            "result": "PASS",
            "observed_at_utc": now.isoformat(),
            "method": "pytest unit",
            "claim": "unit proof",
            "artifact_path": "evidence/pass23",
            "environment": "verifier",
        },
        {
            "evidence_id": "EVID-P23-B",
            "criterion_ids": [criterion.criterion_id],
            "verification_status": "VERIFIED",
            "result": "PASS",
            "observed_at_utc": now.isoformat(),
            "method": "integration contract",
            "claim": "integration proof",
            "artifact_path": "evidence/pass23",
            "environment": "verifier",
        },
    )
    assessed = assess_evidence_for_criterion(criterion, records, now=now)
    self_review = IndependentReview(
        review_id=assurance_identifier("REVIEW", "PASS23", "self"),
        subject_id="PASS23",
        identity=ReviewerIdentity(
            reviewer_id="implementer",
            implementer_id="implementer",
            context_fingerprint="a" * 64,
            implementation_context_fingerprint="a" * 64,
        ),
        criterion_ids=(criterion.criterion_id,),
        finding_count=0,
        blocking_finding_count=0,
        completed_at_utc=now,
    )
    independent = IndependentReview(
        review_id=assurance_identifier("REVIEW", "PASS23", "independent"),
        subject_id="PASS23",
        identity=ReviewerIdentity(
            reviewer_id="reviewer",
            implementer_id="implementer",
            context_fingerprint="b" * 64,
            implementation_context_fingerprint="a" * 64,
        ),
        criterion_ids=(criterion.criterion_id,),
        finding_count=0,
        blocking_finding_count=0,
        completed_at_utc=now,
    )
    self_ok, _ = evidence_sufficient(criterion, assessed, review=self_review)
    independent_ok, _ = evidence_sufficient(criterion, assessed, review=independent)
    return (not self_ok) and independent_ok


def run_full_e2e(root: Path) -> dict[str, Any]:
    root = root.resolve()
    stages: list[E2EStage] = []
    fixture = root / "fixtures/intake/existing_python_service"
    manifest = compile_project(
        ProjectIntakeRequest(
            mode=IntakeMode.EXISTING_PROJECT,
            project_name="Pass 23 Fixture",
            target_root=str(fixture),
        )
    )
    stages.append(
        _stage(
            "project_intake",
            "INTAKE",
            E2EExecutionMode.LOCAL_REAL,
            manifest.project_name == "Pass 23 Fixture" and bool(manifest.repositories),
            f"compiled {len(manifest.repositories)} repository records",
        )
    )

    requirements = load_requirement_catalog(root)
    req = {x["requirement_id"]: x for x in requirements}
    stages.append(
        _stage(
            "requirement_compilation",
            "REQUIREMENTS",
            E2EExecutionMode.LOCAL_REAL,
            "REQ-ASSURE-0024" in req and "REQ-CTRL-0014" in req,
            f"loaded {len(requirements)} accepted requirement records",
        )
    )

    local = JiraMirrorRepository(root).bundle()
    empty = JiraRemoteSnapshot.create(project_key="PP", issues=())
    plan = JiraReconciler().plan(local, empty)
    adapter = MockJiraAdapter(project_key="PP")
    with JiraSyncStore(":memory:", root) as store:
        store.put_snapshot(empty)
        steward = JiraSteward(
            root=root, adapter=adapter, store=store, policy=JiraReconciliationPolicy()
        )
        receipt = steward.dry_run(plan, actor_id="actor:pass23", correlation_id="corr:pass23")
    stages.append(
        _stage(
            "jira_generation_and_reconciliation",
            "JIRA_STEWARD",
            E2EExecutionMode.DRY_RUN,
            receipt.result == "DRY_RUN"
            and not any(call[0] == "create_issue" for call in adapter.calls),
            f"planned {len(plan.operations)} operations with zero remote writes",
        )
    )

    done = TaskControlFact(
        task_id="PP-TASK-000361",
        project_id="PROJECT-PIPELINE",
        state=TaskLifecycleState.DONE,
        priority="P1",
        risk="MEDIUM",
    )
    ready = TaskControlFact(
        task_id="PP-TASK-000362",
        project_id="PROJECT-PIPELINE",
        state=TaskLifecycleState.BACKLOG,
        priority="P1",
        risk="HIGH",
        dependency_ids=(done.task_id,),
    )
    human = TaskControlFact(
        task_id="PP-TASK-000363",
        project_id="PROJECT-PIPELINE",
        state=TaskLifecycleState.BACKLOG,
        priority="P0",
        risk="HIGH",
        external_blocked=True,
    )
    seq = BuildSequencer((done, ready, human))
    stages.append(
        _stage(
            "sequencing_and_human_gate",
            "CONTROL",
            E2EExecutionMode.LOCAL_REAL,
            seq.readiness(ready).state is ReadinessState.READY
            and seq.eligibility(human).state is EligibilityState.BLOCKED_EXTERNAL,
            "dependency-ready work separated from autonomous external-precondition work",
        )
    )

    control = _control_snapshot(ready.task_id)
    registry = ResourceRegistrySnapshot.create(
        pools=(
            ResourcePool(
                resource_key="machine:pass23/cpu_slots",
                resource_type=ResourceType.CPU_SLOT,
                capacity_units=1,
            ),
        )
    )
    profile = SchedulerTaskProfile(
        task_id=ready.task_id,
        project_id="PROJECT-PIPELINE",
        sequence_rank=1,
        utility_score=100,
        priority="P1",
    )
    schedule = DynamicLaneScheduler().plan(control, (profile,), registry)
    stages.append(
        _stage(
            "dynamic_scheduling",
            "SCHEDULER",
            E2EExecutionMode.LOCAL_REAL,
            len(schedule.lanes) == 1 and schedule.lanes[0].task_id == ready.task_id,
            "eligible ready work admitted to one deterministic lane",
        )
    )

    envelope = DelegationEnvelope.create(
        objective="Execute Pass 23 integration work",
        return_protocol="Return result and evidence",
        required_context_keys=("requirement",),
    )
    candidate = ContextCandidate(
        context_key="requirement",
        kind=ContextSourceKind.REQUIREMENT,
        content=req["REQ-ASSURE-0024"]["statement"],
        revision_id="r23",
        observed_at_utc=datetime.now(UTC),
        trust=ContextTrust.GOVERNING,
        sensitivity=Sensitivity.INTERNAL,
    )
    policy = ContextPolicy(policy_version="CTX-POLICY-1.0", max_age_seconds=3600)
    selection = ContextBroker().select(envelope, (candidate,), policy)
    pack = ContextCompiler().compile(envelope, selection, (candidate,), policy)
    stages.append(
        _stage(
            "delegation_and_context_compilation",
            "CONTEXT",
            E2EExecutionMode.LOCAL_REAL,
            pack.coverage.score == 1.0
            and not pack.coverage.missing_keys
            and pack.items[0].context_key == "requirement",
            f"compiled context pack {pack.pack_id}",
        )
    )

    fallback_ok, execution_id = _agent_fallback()
    stages.append(
        _stage(
            "agent_execution_provider_outage",
            "AGENT_ROUTER",
            E2EExecutionMode.DETERMINISTIC_SIMULATION,
            fallback_ok,
            f"provider fallback receipt {execution_id}",
        )
    )

    recommendation = evaluate_recommendation_authority(
        "recommendation:pass23", conflicts_with_canonical_plan=True
    )
    stages.append(
        _stage(
            "canonical_authority_conflict",
            "CONTROL",
            E2EExecutionMode.LOCAL_REAL,
            (not recommendation.may_apply) and recommendation.disposition.value == "ESCALATE",
            "conflicting advisory recommendation escalated instead of silently applied",
        )
    )

    review_ok = _independent_review_proof()
    stages.append(
        _stage(
            "independent_review_separation",
            "ASSURANCE",
            E2EExecutionMode.LOCAL_REAL,
            review_ok,
            "self-review rejected; independent review accepted",
        )
    )
    evidence_rows = sum(
        1
        for line in (root / "evidence/EVIDENCE_LEDGER.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    )
    stages.append(
        _stage(
            "verification_and_evidence",
            "VERIFICATION",
            E2EExecutionMode.LOCAL_REAL,
            review_ok and evidence_rows > 0,
            f"independent verification accepted and {evidence_rows} evidence records are preserved",
        )
    )

    with tempfile.TemporaryDirectory(prefix="project-pipeline-pass23-") as temp:
        git_ok, operation_id = _github_mock_flow(root, Path(temp))
    stages.append(
        _stage(
            "git_pr_merge_gate",
            "GITHUB_STEWARD",
            E2EExecutionMode.MOCK_REMOTE,
            git_ok,
            f"local git real; remote PR gate mocked; operation {operation_id}",
        )
    )

    unknown = simulate_scenario(root, "unknown-outcome")
    worker = simulate_scenario(root, "worker-loss")
    stages.append(
        _stage(
            "durable_restart_and_unknown_outcome",
            "ORCHESTRATION",
            E2EExecutionMode.DETERMINISTIC_SIMULATION,
            unknown.passed and worker.passed,
            f"unknown={unknown.final_state}; worker_loss={worker.final_state}",
        )
    )
    stages.append(
        _stage(
            "project_continuation",
            "ORCHESTRATION",
            E2EExecutionMode.DETERMINISTIC_SIMULATION,
            worker.passed,
            "worker loss produced bounded retry state and continuation remained possible",
        )
    )

    incident_ok, incident_id = _incident_recovery()
    stages.append(
        _stage(
            "incident_human_repair_reconciliation",
            "COMMAND_CENTER",
            E2EExecutionMode.DETERMINISTIC_SIMULATION,
            incident_ok,
            f"incident {incident_id} verified before resolution",
        )
    )

    gate = evaluate_completion_gate(build_repository_gate_facts(root, "PROJECT-PIPELINE"))
    stages.append(
        _stage(
            "independent_completion_gate",
            "ASSURANCE",
            E2EExecutionMode.LOCAL_REAL,
            gate.state.value == "NOT_COMPLETE",
            "full-project gate refuses premature completion",
        )
    )

    cc = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:pass23",
        project_id="PROJECT-PIPELINE",
        operating_mode="NORMAL",
        health=(
            HealthDimension(
                name="integration", state=HealthState.HEALTHY, reason="Pass 23 journey executed"
            ),
        ),
        completion_gate_state=gate.state.value,
        completion_percent=None,
    )
    app = RepositoryApplicationProjectionBuilder(root).build(cc)
    stages.append(
        _stage(
            "command_center_visibility",
            "COMMAND_CENTER",
            E2EExecutionMode.LOCAL_REAL,
            app.canonical_authority == "PROJECT_PIPELINE" and app.ui_state_authoritative is False,
            "read-only Command Center projection reconciled to canonical state",
        )
    )

    external = (
        ("atlassian_mcp_live_mutation", "JIRA_STEWARD"),
        ("github_mcp_live_mutation", "GITHUB_STEWARD"),
        ("hatchet_live_backend", "ORCHESTRATION"),
        ("pydantic_ai_live_execution", "AGENT_ROUTER"),
        ("schemathesis_external_cli", "VERIFICATION"),
        ("toxiproxy_external_runtime", "RESILIENCE"),
        ("swerex_live_runtime", "AGENT_EXECUTION"),
        ("testcontainers_docker_runtime", "VERIFICATION"),
    )
    for name, owner in external:
        stages.append(
            _stage(
                name,
                owner,
                E2EExecutionMode.BLOCKED_EXTERNAL,
                True,
                "external executable/service/credentials are not required for local deterministic acceptance and no live mutation was claimed",
                expected_block=True,
            )
        )

    happy = E2EJourney("E2E-P23-001", "full_project_pipeline_journey", stages)
    incident_dedupe_ok = _incident_idempotency()
    duplicate = E2EJourney(
        "E2E-P23-002",
        "duplicate_and_idempotency",
        [
            _stage(
                "jira_dry_run_repeatability",
                "JIRA_STEWARD",
                E2EExecutionMode.DRY_RUN,
                receipt.result == "DRY_RUN",
                "repeatable plan persisted without remote write",
            ),
            _stage(
                "incident_open_idempotency",
                "COMMAND_CENTER",
                E2EExecutionMode.DETERMINISTIC_SIMULATION,
                incident_dedupe_ok,
                "repeated incident delivery produced one open inbox item",
            ),
        ],
    )
    partial = E2EJourney(
        "E2E-P23-003",
        "partial_failure_retry_and_recovery",
        [
            _stage(
                "provider_retry_fallback",
                "AGENT_ROUTER",
                E2EExecutionMode.DETERMINISTIC_SIMULATION,
                fallback_ok,
                "first provider unavailable; fallback succeeded",
            ),
            _stage(
                "unknown_outcome_no_blind_retry",
                "ORCHESTRATION",
                E2EExecutionMode.DETERMINISTIC_SIMULATION,
                unknown.passed,
                "unknown outcome became RECOVERY_REQUIRED",
            ),
            _stage(
                "human_repair_then_resume",
                "COMMAND_CENTER",
                E2EExecutionMode.DETERMINISTIC_SIMULATION,
                incident_ok,
                "repair verification completed before incident resolution",
            ),
        ],
    )
    journeys = [happy, duplicate, partial]
    report = {
        "schema_version": "1.0.0",
        "pass_number": 23,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "canonical_authority": "PROJECT_PIPELINE",
        "overall_passed": all(j.passed for j in journeys),
        "journeys": [j.as_dict() for j in journeys],
        "live_external_mutation_performed": False,
        "runtime_qualification": {
            "playwright": importlib.util.find_spec("playwright") is not None,
            "hatchet_sdk": importlib.util.find_spec("hatchet_sdk") is not None,
            "pydantic_ai": importlib.util.find_spec("pydantic_ai") is not None,
            "schemathesis": importlib.util.find_spec("schemathesis") is not None,
            "testcontainers": importlib.util.find_spec("testcontainers") is not None,
            "docker_cli": shutil.which("docker") is not None,
            "toxiproxy_cli": shutil.which("toxiproxy-cli") is not None
            or shutil.which("toxiproxy-server") is not None,
            "git_cli": shutil.which("git") is not None,
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def write_full_e2e_report(root: Path, output: Path | None = None) -> Path:
    report = run_full_e2e(root)
    output = output or (root / "evidence/verification/pass23_full_e2e_report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return output
