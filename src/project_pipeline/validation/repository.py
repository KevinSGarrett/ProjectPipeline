from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from project_pipeline.agent_router.validation import validate_agent_router_foundation
from project_pipeline.architecture import validate_architecture
from project_pipeline.assurance.validation import validate_assurance
from project_pipeline.budget import validate_budget_foundation
from project_pipeline.command_center import (
    validate_command_center_application,
    validate_command_center_foundation,
)
from project_pipeline.configuration import validate_runtime_configuration_files
from project_pipeline.context_engine import validate_context_foundation
from project_pipeline.contracts import validate_schemas
from project_pipeline.control import validate_control_foundation
from project_pipeline.convergence import validate_final_convergence
from project_pipeline.dependencies import validate_dependency_lock
from project_pipeline.github_steward import validate_github_steward_foundation
from project_pipeline.intake import validate_intake_foundation
from project_pipeline.io import read_json
from project_pipeline.jira_steward import validate_jira_steward_foundation
from project_pipeline.lifecycle import validate_lifecycle_foundation
from project_pipeline.manifest import verify_manifest
from project_pipeline.orchestration import validate_orchestration_foundation
from project_pipeline.persistence import validate_migration_catalog
from project_pipeline.release_hardening import validate_release_hardening
from project_pipeline.resilience import validate_resilience_foundation
from project_pipeline.scheduler import validate_scheduler_foundation
from project_pipeline.security import validate_security_foundation
from project_pipeline.services.state import validate_project_domain_manifest
from project_pipeline.upstream import validate_upstream_reviews
from project_pipeline.validation.content import (
    check_forbidden_terminology,
    check_markdown_links,
    check_placeholders,
    check_secrets,
)
from project_pipeline.validation.models import ValidationReport
from project_pipeline.validation.product_outcome import validate_product_outcome
from project_pipeline.validation.registries import (
    check_adr_registry,
    check_evidence_ledger,
    check_jira_registry,
    check_json_documents,
    check_plan_registry,
    check_requirement_registry,
    check_requirement_supporting_registries,
    check_source_section_registry,
    check_traceability_exports,
    check_upstream_registry,
)


class RepositoryValidator:
    """Run deterministic repository-contract checks without external dependencies."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.report = ValidationReport(project_root=str(self.root))
        policy_path = self.root / "config" / "repository_policy.json"
        self.policy: dict[str, Any] = read_json(policy_path) if policy_path.exists() else {}

    def _run(self, name: str, check: Callable[[], None]) -> None:
        self.report.checks_run.append(name)
        try:
            check()
        except Exception as error:
            self.report.add(
                "ERROR", "VALIDATOR999", f"Check {name} raised {type(error).__name__}: {error}"
            )

    def validate(self) -> ValidationReport:
        self._run("required_paths", self._check_required_paths)
        self._run("json_documents", lambda: check_json_documents(self.root, self.report))
        self._run("runtime_configuration", self._check_runtime_configuration)
        self._run("dependency_lock", self._check_dependency_lock)
        self._run("generated_schemas", self._check_generated_schemas)
        self._run("project_domain_manifest", self._check_project_domain_manifest)
        self._run("product_outcome", self._check_product_outcome)
        self._run("database_migrations", self._check_database_migrations)
        self._run("project_intake_compiler", self._check_project_intake_compiler)
        self._run("jira_steward", self._check_jira_steward)
        self._run("github_steward", self._check_github_steward)
        self._run("project_control_kernel", self._check_project_control_kernel)
        self._run("dynamic_lane_scheduler", self._check_dynamic_lane_scheduler)
        self._run("agent_router", self._check_agent_router)
        self._run("context_and_delegation", self._check_context_and_delegation)
        self._run("durable_orchestration", self._check_durable_orchestration)
        self._run("budget_governor", self._check_budget_governor)
        self._run("execution_assurance", self._check_execution_assurance)
        self._run("verification_harness", self._check_verification_harness)
        self._run("security_identity_policy", self._check_security_identity_policy)
        self._run("resilience_recovery", self._check_resilience_recovery)
        self._run("command_center", self._check_command_center)
        self._run("command_center_application", self._check_command_center_application)
        self._run("advanced_platform_lifecycle", self._check_advanced_platform_lifecycle)
        self._run("release_hardening", self._check_release_hardening)
        self._run("final_convergence", self._check_final_convergence)
        self._run(
            "forbidden_terminology",
            lambda: check_forbidden_terminology(self.root, self.policy, self.report),
        )
        content_policy = self.policy.get("content_validation", {})
        excluded_roots = (
            content_policy.get("placeholder_excluded_roots", [])
            if isinstance(content_policy, dict)
            else []
        )
        self._run(
            "placeholders",
            lambda: check_placeholders(
                self.root,
                self.report,
                excluded_roots=excluded_roots if isinstance(excluded_roots, list) else (),
            ),
        )
        self._run("secrets", lambda: check_secrets(self.root, self.report))
        self._run("markdown_links", lambda: check_markdown_links(self.root, self.report))

        plan_ids: set[str] = set()
        section_index: dict[str, Any] = {}
        issues: dict[str, dict[str, Any]] = {}
        requirements: dict[str, dict[str, Any]] = {}

        def plans() -> None:
            nonlocal plan_ids, section_index
            plan_ids, section_index = check_plan_registry(self.root, self.report)

        def jira() -> None:
            nonlocal issues
            issues = check_jira_registry(self.root, self.report, plan_ids, section_index)

        def requirement_check() -> None:
            nonlocal requirements
            requirements = check_requirement_registry(self.root, self.report, plan_ids, issues)

        self._run("plans", plans)
        self._run("jira", jira)
        self._run("requirements", requirement_check)
        self._run(
            "requirement_supporting_registries",
            lambda: check_requirement_supporting_registries(
                self.root, self.report, requirements, plan_ids, section_index, issues
            ),
        )
        self._run(
            "source_section_registry",
            lambda: check_source_section_registry(self.root, self.report, requirements),
        )
        self._run(
            "traceability_exports",
            lambda: check_traceability_exports(self.root, self.report, requirements),
        )
        self._run("architecture_decisions", lambda: check_adr_registry(self.root, self.report))
        self._run("architecture_registry", self._check_architecture_registry)
        self._run("upstream_registry", lambda: check_upstream_registry(self.root, self.report))
        self._run("upstream_reviews", self._check_upstream_reviews)
        self._run("evidence_ledger", lambda: check_evidence_ledger(self.root, self.report))
        self._run("manifest", self._check_manifest)
        return self.report

    def _check_runtime_configuration(self) -> None:
        for error in validate_runtime_configuration_files(self.root):
            self.report.add("ERROR", "CONFIG001", error, "config/runtime")

    def _check_dependency_lock(self) -> None:
        for error in validate_dependency_lock(self.root):
            self.report.add("ERROR", "DEPEND001", error, "requirements/environment.lock.json")

    def _check_generated_schemas(self) -> None:
        for error in validate_schemas(self.root):
            self.report.add("ERROR", "SCHEMA001", error, "schemas")

    def _check_project_domain_manifest(self) -> None:
        for error in validate_project_domain_manifest(self.root):
            self.report.add("ERROR", "PROJECTSTATE001", error, "config/project_manifest.json")

    def _check_product_outcome(self) -> None:
        for error in validate_product_outcome(self.root):
            self.report.add("ERROR", "PRODUCT001", error, "config/product_outcome.json")

    def _check_database_migrations(self) -> None:
        for error in validate_migration_catalog(self.root):
            self.report.add("ERROR", "MIGRATION001", error, "database/MIGRATION_CATALOG.json")

    def _check_project_intake_compiler(self) -> None:
        for error in validate_intake_foundation(self.root):
            self.report.add("ERROR", "INTAKE001", error, "src/project_pipeline/intake")

    def _check_jira_steward(self) -> None:
        for error in validate_jira_steward_foundation(self.root):
            self.report.add("ERROR", "JIRASTEWARD001", error, "src/project_pipeline/jira_steward")

    def _check_github_steward(self) -> None:
        for error in validate_github_steward_foundation(self.root):
            self.report.add(
                "ERROR", "GITHUBSTEWARD001", error, "src/project_pipeline/github_steward"
            )

    def _check_project_control_kernel(self) -> None:
        for error in validate_control_foundation(self.root):
            self.report.add("ERROR", "CONTROL001", error, "src/project_pipeline/control")

    def _check_dynamic_lane_scheduler(self) -> None:
        for error in validate_scheduler_foundation(self.root):
            self.report.add("ERROR", "SCHEDULER001", error, "src/project_pipeline/scheduler")

    def _check_agent_router(self) -> None:
        for error in validate_agent_router_foundation(self.root):
            self.report.add("ERROR", "AGENTROUTER001", error, "src/project_pipeline/agent_router")

    def _check_context_and_delegation(self) -> None:
        for error in validate_context_foundation(self.root):
            self.report.add("ERROR", "CONTEXT001", error, "src/project_pipeline/context_engine")

    def _check_durable_orchestration(self) -> None:
        for error in validate_orchestration_foundation(self.root):
            self.report.add("ERROR", "ORCH001", error, "src/project_pipeline/orchestration")

    def _check_budget_governor(self) -> None:
        for error in validate_budget_foundation(self.root):
            self.report.add("ERROR", "BUDGET001", error, "src/project_pipeline/budget")

    def _check_execution_assurance(self) -> None:
        for error in validate_assurance(self.root):
            self.report.add("ERROR", "ASSURE001", error, "src/project_pipeline/assurance")

    def _check_verification_harness(self) -> None:
        from project_pipeline.verification.validation import validate_verification_harness

        for error in validate_verification_harness(self.root):
            self.report.add("ERROR", "VERIFY001", error, "src/project_pipeline/verification")

    def _check_security_identity_policy(self) -> None:
        for error in validate_security_foundation(self.root):
            self.report.add("ERROR", "SECURITY001", error, "src/project_pipeline/security")

    def _check_resilience_recovery(self) -> None:
        for error in validate_resilience_foundation(self.root):
            self.report.add("ERROR", "RESILIENCE001", error, "src/project_pipeline/resilience")

    def _check_command_center(self) -> None:
        for error in validate_command_center_foundation(self.root):
            self.report.add(
                "ERROR", "COMMANDCENTER001", error, "src/project_pipeline/command_center"
            )

    def _check_command_center_application(self) -> None:
        for error in validate_command_center_application(self.root):
            self.report.add("ERROR", "COMMANDCENTERAPP001", error, "apps/command_center")

    def _check_advanced_platform_lifecycle(self) -> None:
        for error in validate_lifecycle_foundation(self.root):
            self.report.add("ERROR", "LIFECYCLE001", error, "src/project_pipeline/lifecycle")

    def _check_release_hardening(self) -> None:
        for error in validate_release_hardening(self.root):
            self.report.add("ERROR", "RELEASEHARDEN001", error, "release")

    def _check_final_convergence(self) -> None:
        for error in validate_final_convergence(self.root):
            self.report.add(
                "ERROR", "CONVERGENCE001", error, "release/final_convergence_audit_r25.json"
            )

    def _check_architecture_registry(self) -> None:
        for error in validate_architecture(self.root):
            self.report.add("ERROR", "ARCHREG001", error, "architecture")

    def _check_upstream_reviews(self) -> None:
        for error in validate_upstream_reviews(self.root):
            self.report.add("ERROR", "UPREVIEW001", error, "provenance/upstream_registry.json")

    def _check_required_paths(self) -> None:
        if not self.policy:
            self.report.add(
                "ERROR",
                "STRUCT000",
                "Repository policy is missing or unreadable",
                "config/repository_policy.json",
            )
            return
        required = self.policy.get("required_paths", [])
        if not isinstance(required, list):
            self.report.add(
                "ERROR",
                "STRUCT001",
                "required_paths is not a list",
                "config/repository_policy.json",
            )
            return
        for relative in required:
            if not isinstance(relative, str):
                self.report.add(
                    "ERROR",
                    "STRUCT002",
                    "required_paths contains a non-string",
                    "config/repository_policy.json",
                )
                continue
            if not (self.root / relative).exists():
                self.report.add(
                    "ERROR", "STRUCT003", f"Required path is missing: {relative}", relative
                )
        for required_manifest in ("PROJECT_MANIFEST.json", "FILE_MANIFEST.sha256"):
            if not (self.root / required_manifest).exists():
                self.report.add(
                    "ERROR",
                    "STRUCT004",
                    f"Generated manifest is missing: {required_manifest}",
                    required_manifest,
                )

    def _check_manifest(self) -> None:
        for error in verify_manifest(self.root):
            self.report.add("ERROR", "MANIFEST001", error, "PROJECT_MANIFEST.json")
        manifest_path = self.root / "PROJECT_MANIFEST.json"
        text_path = self.root / "FILE_MANIFEST.sha256"
        if not manifest_path.exists() or not text_path.exists():
            return
        manifest = read_json(manifest_path)
        expected = [f"{item['sha256']}  {item['path']}" for item in manifest.get("files", [])]
        observed = text_path.read_text(encoding="utf-8").splitlines()
        if observed != expected:
            self.report.add(
                "ERROR",
                "MANIFEST002",
                "FILE_MANIFEST.sha256 differs from project manifest",
                "FILE_MANIFEST.sha256",
            )
