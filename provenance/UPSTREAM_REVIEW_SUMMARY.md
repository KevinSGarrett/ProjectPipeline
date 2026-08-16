# Upstream Evaluation and Use Summary

- Cataloged repositories: `116`
- Focused, deep, or source-level reviews complete: `68`
- Terminal catalog dispositions: `116`
- Remaining EVALUATE_LATER entries: `0`
- Direct dependency/component selections: `60`
- Implemented upstream usages: `60`
- Active runtime dependencies: `1`
- Optional adapters implemented: `24`
- External CLI adapters implemented: `22`
- Bounded source adaptations approved: `2`
- Selected but not activated: `13`

## Reviewed repositories

### UPSTREAM-003 — ag-ui-protocol/ag-ui

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `b70b564fc99504bf57a1d82feab714d67f85a563`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Director Chat event-compatibility adapter.
- Integration paths: `src/project_pipeline/command_center/agui.py, src/project_pipeline/command_center/realtime.py, tests/test_command_center_agui.py, docs/command_center/backend_realtime_api.md`
- Review: [`provenance/reviews/PASS-21_director_incident_notifications_upstream_review.md`](reviews/PASS-21_director_incident_notifications_upstream_review.md)

### UPSTREAM-007 — aquasecurity/trivy

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `d98911ea338b061f8bef0baeef85b35660013b32`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Trivy as an external container/IaC/filesystem vulnerability scanner; activation requires pinned release and compatibility evidence.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py, tests/test_security_upstream_adapters.py`
- Review: [`provenance/reviews/UPSTREAM-007_security_review.md`](reviews/UPSTREAM-007_security_review.md)

### UPSTREAM-009 — assistant-ui/assistant-ui

- Disposition: `MINE_IMPLEMENTATION_PATTERN`
- Usage state: `NOT_SELECTED`
- License: `MIT`
- Inspected revision: `assistant-ui/assistant-ui@metadata-snapshot-20260815T224500Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine production React chat composition, streaming, retry, attachment, accessibility, and tool-call UX patterns for the later Director Chat client; do not activate it in the Pass 19 backend.
- Integration paths: `none`
- Review: [`provenance/reviews/PASS-21_director_incident_notifications_upstream_review.md`](reviews/PASS-21_director_incident_notifications_upstream_review.md)

### UPSTREAM-011 — atlassian/atlassian-mcp-server

- Disposition: `ADAPT_COMPONENT`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `94a30436435fb526a29f820f5f46250870eb75a0`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Prefer the official Atlassian MCP server for an optional governed Jira/Confluence tool adapter; remote mutations remain policy-gated.
- Integration paths: `src/project_pipeline/upstream_integrations/mcp.py`
- Review: [`provenance/reviews/UPSTREAM-011_source_level_candidate.md`](reviews/UPSTREAM-011_source_level_candidate.md)

### UPSTREAM-012 — BerriAI/litellm

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `87abb8781ee2e586858c9e9943ecb789e316af96`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Source-selected multi-provider model gateway whose activation is blocked pending license and public release-channel approval.
- Integration paths: `src/project_pipeline/agent_router/adapters.py, src/project_pipeline/agent_router/router.py, src/project_pipeline/budget/service.py, tests/test_litellm_adapter.py, tests/test_budget_integration.py`
- Review: [`provenance/reviews/UPSTREAM-012.md`](reviews/UPSTREAM-012.md)

### UPSTREAM-013 — binwiederhier/ntfy

- Disposition: `ADAPT_COMPONENT`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0 OR GPL-2.0`
- Inspected revision: `binwiederhier/ntfy@metadata-snapshot-20260815T062737Z`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Implement an optional self-hosted notification adapter around ntfy; keep notification policy and deduplication internal.
- Integration paths: `src/project_pipeline/command_center/notifications.py, config/command_center_policy.json, tests/test_command_center_pass21.py`
- Review: [`provenance/reviews/PASS-21_director_incident_notifications_upstream_review.md`](reviews/PASS-21_director_incident_notifications_upstream_review.md)

### UPSTREAM-017 — caronc/apprise

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `BSD-2-Clause`
- Inspected revision: `caronc/apprise@metadata-snapshot-20260815T062737Z`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Apprise as a multi-channel notification delivery library behind the Notification Broker.
- Integration paths: `src/project_pipeline/command_center/notifications.py, config/command_center_policy.json, pyproject.toml, tests/test_command_center_pass21.py`
- Review: [`provenance/reviews/PASS-21_director_incident_notifications_upstream_review.md`](reviews/PASS-21_director_incident_notifications_upstream_review.md)

### UPSTREAM-023 — CopilotKit/CopilotKit

- Disposition: `MINE_IMPLEMENTATION_PATTERN`
- Usage state: `NOT_SELECTED`
- License: `MIT`
- Inspected revision: `CopilotKit/CopilotKit@metadata-snapshot-20260815T224500Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine generative UI, human-in-the-loop, and shared-state interaction patterns while explicitly rejecting frontend-writable shared state as canonical Project Pipeline state.
- Integration paths: `none`
- Review: [`provenance/reviews/PASS-21_director_incident_notifications_upstream_review.md`](reviews/PASS-21_director_incident_notifications_upstream_review.md)

### UPSTREAM-026 — dbos-inc/dbos-transact-py

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `NOT_SELECTED`
- License: `MIT`
- Inspected revision: `e0b742c2b9100676ea4b92cc71716e0b4ffa6108`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualified PostgreSQL-centered durable execution fallback and benchmark candidate.
- Integration paths: `none`
- Review: [`provenance/reviews/UPSTREAM-026.md`](reviews/UPSTREAM-026.md)

### UPSTREAM-028 — devcontainers/spec

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `ARCHITECTURE_PATTERN_ADOPTED`
- License: `CC-BY-4.0 AND MIT`
- Inspected revision: `devcontainers/spec@metadata-snapshot-20260815T233400Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Use the Dev Container specification as a portability/reference standard without making it mandatory for Windows-first operation.
- Integration paths: `src/project_pipeline/lifecycle/environments.py, config/platform_lifecycle_policy.json, tests/test_pass22_platform_lifecycle.py`
- Review: [`provenance/reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md`](reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md)

### UPSTREAM-029 — docker/mcp-gateway

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `24b028f4f9aac85ce1a1057c5e8d739836e7c18d`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `true`
- Project Pipeline role: Initial MCP lifecycle and isolation gateway behind GovernedToolPort.
- Integration paths: `src/project_pipeline/agent_router/docker_mcp_gateway.py, src/project_pipeline/upstream_data/docker_mcp_gateway_security_defaults.json, tests/test_docker_mcp_gateway.py`
- Review: [`provenance/reviews/UPSTREAM-029_docker_mcp-gateway.md`](reviews/UPSTREAM-029_docker_mcp-gateway.md)

### UPSTREAM-030 — docling-project/docling

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `61d76f1ff3f8428065465889f7b4577da7df704c`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Docling for structured document/PDF ingestion when richer extraction than lightweight converters is required.
- Integration paths: `src/project_pipeline/upstream_integrations/context.py`
- Review: [`provenance/reviews/UPSTREAM-030_context_source_review.md`](reviews/UPSTREAM-030_context_source_review.md)

### UPSTREAM-035 — FiloSottile/age

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `BSD-3-Clause`
- Inspected revision: `706dfc1e799a03443ae46023502bd88d4e9e324f`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Local recipient/key mechanism for SOPS.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py, src/project_pipeline/security/backends.py, tests/test_security_secrets.py`
- Review: [`provenance/reviews/UPSTREAM-035.md`](reviews/UPSTREAM-035.md)

### UPSTREAM-036 — Fission-AI/OpenSpec

- Disposition: `MINE_IMPLEMENTATION_PATTERN`
- Usage state: `IMPLEMENTATION_PATTERN_ADOPTED`
- License: `MIT`
- Inspected revision: `Fission-AI/OpenSpec@metadata-snapshot-20260815T233400Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine spec-driven change-management patterns while keeping Project Pipeline requirements/plans/Jira authoritative.
- Integration paths: `src/project_pipeline/lifecycle/contracts.py, tests/test_pass22_platform_lifecycle.py`
- Review: [`provenance/reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md`](reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md)

### UPSTREAM-039 — getsops/sops

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `MPL-2.0`
- Inspected revision: `30332a959e3d987f622702519f6b52d8ff81e1dc`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Encrypted structured configuration.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py, src/project_pipeline/security/backends.py, tests/test_security_secrets.py`
- Review: [`provenance/reviews/UPSTREAM-039.md`](reviews/UPSTREAM-039.md)

### UPSTREAM-040 — ggml-org/llama.cpp

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `ggml-org/llama.cpp@metadata-snapshot-20260815T062737Z`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify llama.cpp as a local model runtime for offline/degraded operation behind the provider/model gateway.
- Integration paths: `src/project_pipeline/resilience/local_models.py, src/project_pipeline/upstream_integrations/resilience.py, tests/test_resilience_upstream_adapters.py`
- Review: [`provenance/reviews/resilience_local_runtime_backup_review.md`](reviews/resilience_local_runtime_backup_review.md)

### UPSTREAM-041 — github/github-mcp-server

- Disposition: `ADAPT_COMPONENT`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `0ea1f775a7c73eff1bd2e25904d01136756bbfe2`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Implement an optional official GitHub MCP adapter/toolset profile while preserving Repository Steward write policy.
- Integration paths: `src/project_pipeline/upstream_integrations/mcp.py`
- Review: [`provenance/reviews/UPSTREAM-041_source_level_candidate.md`](reviews/UPSTREAM-041_source_level_candidate.md)

### UPSTREAM-042 — github/spec-kit

- Disposition: `MINE_IMPLEMENTATION_PATTERN`
- Usage state: `IMPLEMENTATION_PATTERN_ADOPTED`
- License: `MIT`
- Inspected revision: `github/spec-kit@metadata-snapshot-20260815T233400Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine specification-to-implementation workflow patterns; Project Pipeline already owns the canonical compiler/control semantics.
- Integration paths: `src/project_pipeline/lifecycle/contracts.py, src/project_pipeline/lifecycle/qualification.py, tests/test_pass22_platform_lifecycle.py`
- Review: [`provenance/reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md`](reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md)

### UPSTREAM-043 — gitleaks/gitleaks

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `b58d3f102cf3a2c84cb7f923d05c25c9b1aed84b`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Gitleaks as a repository secret-scanning CLI enforced locally and in CI.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py`
- Review: [`provenance/reviews/UPSTREAM-043_integration_review.md`](reviews/UPSTREAM-043_integration_review.md)

### UPSTREAM-045 — google-gemini/gemini-cli

- Disposition: `ADAPT_COMPONENT`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `2a87e7be103308b8734246097ba723cc7deb4122`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Implement a Gemini CLI worker adapter as one interchangeable coding-agent runtime.
- Integration paths: `src/project_pipeline/upstream_integrations/workers.py`
- Review: [`provenance/reviews/UPSTREAM-045_integration_review.md`](reviews/UPSTREAM-045_integration_review.md)

### UPSTREAM-046 — google/or-tools

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `98c165af62df62b3056c2ee0fca66b24e79097cb`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Bounded lane/resource optimizer whose output is revalidated.
- Integration paths: `src/project_pipeline/scheduler/ortools_optimizer.py, src/project_pipeline/scheduler/engine.py, tests/test_ortools_optimizer.py`
- Review: [`provenance/reviews/UPSTREAM-046.md`](reviews/UPSTREAM-046.md)

### UPSTREAM-047 — google/osv-scanner

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `567f3ea998f1241e60ec3ca9c4cc9e30809cd820`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify OSV-Scanner for dependency vulnerability and license scanning; remediation execution remains disabled by default.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py`
- Review: [`provenance/reviews/UPSTREAM-047_integration_review.md`](reviews/UPSTREAM-047_integration_review.md)

### UPSTREAM-050 — hatchet-dev/hatchet

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `4253c86ca3a763a6065b4134a6017a630b610061`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Initial durable execution backend behind DurableExecutionPort.
- Integration paths: `src/project_pipeline/orchestration/adapters.py, src/project_pipeline/orchestration/ports.py, tests/test_orchestration_adapters.py`
- Review: [`provenance/reviews/UPSTREAM-050.md`](reviews/UPSTREAM-050.md)

### UPSTREAM-051 — HypothesisWorks/hypothesis

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `SELECTED_NOT_ACTIVATED`
- License: `MPL-2.0`
- Inspected revision: `16f24b76015dbaabca40608eb9e73b46ac64e249`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Hypothesis for property-based tests of deterministic state, scheduling, and reconciliation invariants.
- Integration paths: `none`
- Review: [`provenance/reviews/PASS-15_verification_evaluation_upstream_review.md`](reviews/PASS-15_verification_evaluation_upstream_review.md)

### UPSTREAM-052 — IBM/mcp-context-forge

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `ARCHITECTURE_PATTERN_ADOPTED`
- License: `Apache-2.0`
- Inspected revision: `6004d236479c12ed2571d9bf9dc5cc20bf3aead7`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Later-only advanced MCP federation option.
- Integration paths: `src/project_pipeline/context_engine/firewall.py, src/project_pipeline/context_engine/broker.py`
- Review: [`provenance/reviews/UPSTREAM-052_context_architecture_adoption.md`](reviews/UPSTREAM-052_context_architecture_adoption.md)

### UPSTREAM-053 — infracost/infracost

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `0c473ade0fd0d725fe8f5edd719ef634d9594690`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: External IaC cost-preflight evidence provider for budget admission; never an infrastructure or budget authority.
- Integration paths: `src/project_pipeline/budget/infracost.py, tests/test_budget_infracost.py, provenance/reviews/UPSTREAM-053_budget_review.md`
- Review: [`provenance/reviews/UPSTREAM-053_budget_review.md`](reviews/UPSTREAM-053_budget_review.md)

### UPSTREAM-055 — jdx/mise

- Disposition: `MINE_IMPLEMENTATION_PATTERN`
- Usage state: `IMPLEMENTATION_PATTERN_ADOPTED`
- License: `MIT`
- Inspected revision: `jdx/mise@metadata-snapshot-20260815T233400Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine reproducible tool-version/environment management patterns; keep platform bootstrap independently operable.
- Integration paths: `src/project_pipeline/lifecycle/qualification.py, adr/ADR-0027_keep_project_native_locks_canonical_with_optional_mise_and_devcontainer_profiles.md, tests/test_pass22_platform_lifecycle.py`
- Review: [`provenance/reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md`](reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md)

### UPSTREAM-058 — kvcache-ai/ktransformers

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `IMPLEMENTATION_PATTERN_ADOPTED`
- License: `Apache-2.0`
- Inspected revision: `kvcache-ai/ktransformers@metadata-snapshot-20260815T062737Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine memory-efficient local inference techniques for constrained GPUs/CPUs; no baseline dependency selected.
- Integration paths: `src/project_pipeline/resilience/local_models.py, provenance/reviews/resilience_local_runtime_backup_review.md, tests/test_resilience_upstream_adapters.py`
- Review: [`provenance/reviews/resilience_local_runtime_backup_review.md`](reviews/resilience_local_runtime_backup_review.md)

### UPSTREAM-059 — langfuse/langfuse

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `ARCHITECTURE_PATTERN_ADOPTED`
- License: `MIT`
- Inspected revision: `ab58010c81339ffb3e19fc491d71733cf4f10f6a`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Alternative observability and evaluation platform retained for later comparison; OpenTelemetry remains the contract and OpenLIT is the initial agent instrumentation profile.
- Integration paths: `src/project_pipeline/domain/budget.py, src/project_pipeline/budget/service.py, tests/test_budget_domain.py`
- Review: [`provenance/reviews/UPSTREAM-059.md`](reviews/UPSTREAM-059.md)

### UPSTREAM-061 — max-sixty/worktrunk

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `MIT OR Apache-2.0`
- Inspected revision: `2d4b6d8ac187dbd6e700e8c3e7ff2be0507d8c85`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Selected Git worktree lifecycle implementation behind RepositoryWorkspacePort and Repository Steward.
- Integration paths: `src/project_pipeline/github_steward/worktrunk.py, tests/test_worktrunk_adapter.py`
- Review: [`provenance/reviews/UPSTREAM-061_max-sixty_worktrunk.md`](reviews/UPSTREAM-061_max-sixty_worktrunk.md)

### UPSTREAM-062 — microsoft/markitdown

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `fd239d5d2be43d9b68329730206b9312c7d5a388`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify MarkItDown as the lightweight document-to-text conversion path for context ingestion.
- Integration paths: `src/project_pipeline/upstream_integrations/context.py`
- Review: [`provenance/reviews/UPSTREAM-062_context_source_review.md`](reviews/UPSTREAM-062_context_source_review.md)

### UPSTREAM-063 — microsoft/playwright

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `a0af4bf3ae711b062fbc31d1655f76af870817c1`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Browser acceptance and evidence capture.
- Integration paths: `src/project_pipeline/verification/browser.py, src/project_pipeline/verification/harness.py`
- Review: [`provenance/reviews/UPSTREAM-063.md`](reviews/UPSTREAM-063.md)

### UPSTREAM-064 — microsoft/playwright-mcp

- Disposition: `ADAPT_COMPONENT`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `7e0457a7cbf88823bf0146d12c46ae12c6818247`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Implement an optional Playwright MCP adapter for structured browser tooling while Playwright remains the core automation runtime.
- Integration paths: `src/project_pipeline/verification/external_tools.py`
- Review: [`provenance/reviews/PASS-15_verification_evaluation_upstream_review.md`](reviews/PASS-15_verification_evaluation_upstream_review.md)

### UPSTREAM-065 — mlflow/mlflow

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `IMPLEMENTATION_PATTERN_ADOPTED`
- License: `Apache-2.0`
- Inspected revision: `9355281ca38ff7e288161f0a71022400f8197175`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Budget-observability comparison source for trace-level token usage and cost aggregation.
- Integration paths: `src/project_pipeline/budget/forecast.py, src/project_pipeline/domain/budget.py, tests/test_budget_forecast.py, provenance/reviews/UPSTREAM-065_budget_review.md`
- Review: [`provenance/reviews/UPSTREAM-065_budget_review.md`](reviews/UPSTREAM-065_budget_review.md)

### UPSTREAM-068 — mostlygeek/llama-swap

- Disposition: `ADAPT_COMPONENT`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `mostlygeek/llama-swap@metadata-snapshot-20260815T062737Z`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Implement an optional llama-swap gateway adapter for local model hot-swap/fallback behavior.
- Integration paths: `src/project_pipeline/resilience/local_models.py, src/project_pipeline/upstream_integrations/resilience.py, tests/test_resilience_upstream_adapters.py`
- Review: [`provenance/reviews/resilience_local_runtime_backup_review.md`](reviews/resilience_local_runtime_backup_review.md)

### UPSTREAM-070 — networkx/networkx

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `ACTIVE_RUNTIME`
- License: `BSD-3-Clause`
- Inspected revision: `9266db885598a9d0b8f2d24ac6fef877e9137b96`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Authoritative graph-analysis library behind internal graph semantics.
- Integration paths: `src/project_pipeline/control/graph.py, src/project_pipeline/scheduler/conflicts.py, src/project_pipeline/scheduler/engine.py`
- Review: [`provenance/reviews/UPSTREAM-070.md`](reviews/UPSTREAM-070.md)

### UPSTREAM-072 — ollama/ollama

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `ollama/ollama@metadata-snapshot-20260815T062737Z`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Ollama as an optional local model service behind the provider-neutral model gateway.
- Integration paths: `src/project_pipeline/resilience/local_models.py, src/project_pipeline/upstream_integrations/resilience.py, tests/test_resilience_upstream_adapters.py`
- Review: [`provenance/reviews/resilience_local_runtime_backup_review.md`](reviews/resilience_local_runtime_backup_review.md)

### UPSTREAM-073 — openai/codex

- Disposition: `ADAPT_COMPONENT`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `85fc4def358b7df21883e72ae8dda43a0f572f32`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Implement an OpenAI Codex worker adapter as an interchangeable coding-agent runtime with Project Pipeline-owned task contracts.
- Integration paths: `src/project_pipeline/upstream_integrations/workers.py`
- Review: [`provenance/reviews/UPSTREAM-073_integration_review.md`](reviews/UPSTREAM-073_integration_review.md)

### UPSTREAM-074 — openai/symphony

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `ARCHITECTURE_PATTERN_ADOPTED`
- License: `Apache-2.0`
- Inspected revision: `8001b52e3062495a16e520e4ceaf8f9de868c4d0`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine Symphony orchestrator/agent-runner/workspace and live-E2E patterns; Project Pipeline retains deterministic control authority.
- Integration paths: `src/project_pipeline/orchestration/service.py, src/project_pipeline/orchestration/recovery.py, tests/test_orchestration_recovery.py`
- Review: [`provenance/reviews/UPSTREAM-074_source_level_candidate.md`](reviews/UPSTREAM-074_source_level_candidate.md)

### UPSTREAM-075 — openbao/openbao

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MPL-2.0`
- Inspected revision: `9c17d73cb4a71690d32d7ed223f9bc8f241f9157`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Later optional dynamic secret and certificate broker.
- Integration paths: `src/project_pipeline/security/backends.py, src/project_pipeline/security/secrets.py, tests/test_security_secrets.py`
- Review: [`provenance/reviews/UPSTREAM-075.md`](reviews/UPSTREAM-075.md)

### UPSTREAM-077 — openlit/openlit

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `24224bdfad8628c639742e49fddc303675067416`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Agent/model instrumentation profile over OpenTelemetry.
- Integration paths: `src/project_pipeline/observability/openlit.py, src/project_pipeline/domain/budget.py, tests/test_openlit_bridge.py, tests/test_budget_domain.py`
- Review: [`provenance/reviews/UPSTREAM-077.md`](reviews/UPSTREAM-077.md)

### UPSTREAM-078 — open-policy-agent/conftest

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `c149d816bb161496cdb2402a720fa5e291236690`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Configuration and infrastructure Rego preflight.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py, policies/security/action_policy.rego, tests/test_security_upstream_adapters.py`
- Review: [`provenance/reviews/UPSTREAM-078.md`](reviews/UPSTREAM-078.md)

### UPSTREAM-079 — open-policy-agent/opa

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `16b5a013726fff3c2197f98ac4afcd6d2218588a`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Runtime declarative policy engine.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py, policies/security/action_policy.rego, tests/test_security_upstream_adapters.py`
- Review: [`provenance/reviews/UPSTREAM-079.md`](reviews/UPSTREAM-079.md)

### UPSTREAM-080 — oraios/serena

- Disposition: `MINE_IMPLEMENTATION_PATTERN`
- Usage state: `IMPLEMENTATION_PATTERN_ADOPTED`
- License: `MIT`
- Inspected revision: `93ec043105f5ee4f5ff64ea0158041500d2cdc65`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine semantic repository navigation/editing patterns for context and code intelligence; no direct authority granted.
- Integration paths: `src/project_pipeline/context_engine/broker.py, src/project_pipeline/context_engine/compiler.py`
- Review: [`provenance/reviews/UPSTREAM-080_context_source_review.md`](reviews/UPSTREAM-080_context_source_review.md)

### UPSTREAM-081 — ossf/scorecard

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `d1fab88f54636ff366076edfc5c239f97b3c8e66`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify OSSF Scorecard for upstream/repository security-posture evidence.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py, tests/test_security_upstream_adapters.py`
- Review: [`provenance/reviews/UPSTREAM-081_security_review.md`](reviews/UPSTREAM-081_security_review.md)

### UPSTREAM-082 — pgbackrest/pgbackrest

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `pgbackrest/pgbackrest@metadata-snapshot-20260815T062737Z`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify pgBackRest as the PostgreSQL-specific backup/restore implementation for production profiles.
- Integration paths: `src/project_pipeline/resilience/backup.py, src/project_pipeline/upstream_integrations/resilience.py, tests/test_resilience_upstream_adapters.py`
- Review: [`provenance/reviews/resilience_local_runtime_backup_review.md`](reviews/resilience_local_runtime_backup_review.md)

### UPSTREAM-083 — pgvector/pgvector

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `SELECTED_NOT_ACTIVATED`
- License: `PostgreSQL`
- Inspected revision: `1a79ebccc2ab3131eb6fcb97aae1188606c410a3`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Default PostgreSQL semantic retrieval extension.
- Integration paths: `none`
- Review: [`provenance/reviews/UPSTREAM-083_pgvector_pgvector.md`](reviews/UPSTREAM-083_pgvector_pgvector.md)

### UPSTREAM-084 — pingdotgg/t3code

- Disposition: `MINE_IMPLEMENTATION_PATTERN`
- Usage state: `NOT_SELECTED`
- License: `MIT`
- Inspected revision: `pingdotgg/t3code@metadata-snapshot-20260815T224500Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine compact coding-agent control-surface, session, and task-switching patterns for Command Center operator workflows.
- Integration paths: `none`
- Review: [`provenance/reviews/PASS-19_command_center_upstream_review.md`](reviews/PASS-19_command_center_upstream_review.md)

### UPSTREAM-085 — promptfoo/promptfoo

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `fded938b65a81e12070a66e90ca4ad2d42a8062e`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify promptfoo for model/agent evaluation and red-team scenarios behind Project Pipeline evidence policy.
- Integration paths: `src/project_pipeline/upstream_integrations/evaluation.py`
- Review: [`provenance/reviews/PASS-15_verification_evaluation_upstream_review.md`](reviews/PASS-15_verification_evaluation_upstream_review.md)

### UPSTREAM-086 — pydantic/pydantic-ai

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `25a70926cfafdfc63b3d32c1b5f2c7f139e2c58c`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `true`
- Project Pipeline role: Typed advisory-agent adapter.
- Integration paths: `src/project_pipeline/agent_router/pydantic_ai_adapter.py, src/project_pipeline/upstream_data/pydantic_ai_provider_compatibility.json, tests/test_pydantic_ai_adapter.py`
- Review: [`provenance/reviews/UPSTREAM-086.md`](reviews/UPSTREAM-086.md)

### UPSTREAM-089 — renovatebot/renovate

- Disposition: `REJECT`
- Usage state: `NOT_SELECTED`
- License: `AGPL-3.0-only`
- Inspected revision: `renovatebot/renovate@metadata-snapshot-20260815T233400Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Renovate as an external dependency-update automation service; source incorporation is not required.
- Integration paths: `none`
- Review: [`provenance/reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md`](reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md)

### UPSTREAM-090 — restic/restic

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `BSD-2-Clause`
- Inspected revision: `restic/restic@metadata-snapshot-20260815T062737Z`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify restic as the general encrypted repository/artifact backup tool for portable/offsite profiles.
- Integration paths: `src/project_pipeline/resilience/backup.py, src/project_pipeline/upstream_integrations/resilience.py, tests/test_resilience_upstream_adapters.py`
- Review: [`provenance/reviews/resilience_local_runtime_backup_review.md`](reviews/resilience_local_runtime_backup_review.md)

### UPSTREAM-092 — schemathesis/schemathesis

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `c60bde9733dad2fc4ef8f6451f58a10e8c7b6663`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Schemathesis for property-based OpenAPI/API contract testing.
- Integration paths: `src/project_pipeline/verification/external_tools.py`
- Review: [`provenance/reviews/PASS-15_verification_evaluation_upstream_review.md`](reviews/PASS-15_verification_evaluation_upstream_review.md)

### UPSTREAM-093 — Shopify/toxiproxy

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `94d6d4b3c385e48534622b138da61e95014196d5`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Toxiproxy for deterministic network fault injection in resilience tests.
- Integration paths: `src/project_pipeline/upstream_integrations/resilience.py, src/project_pipeline/verification/external_tools.py, src/project_pipeline/verification/faults.py, tests/test_resilience_upstream_adapters.py`
- Review: [`provenance/reviews/resilience_local_runtime_backup_review.md`](reviews/resilience_local_runtime_backup_review.md)

### UPSTREAM-094 — sigstore/cosign

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `8b8c87b68a75f70c12e1adf25f9bb87f24abea7e`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Cosign for artifact/container signature verification and signing workflows.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py`
- Review: [`provenance/reviews/UPSTREAM-094_integration_review.md`](reviews/UPSTREAM-094_integration_review.md)

### UPSTREAM-095 — sipyourdrink-ltd/bernstein

- Disposition: `MINE_IMPLEMENTATION_PATTERN`
- Usage state: `IMPLEMENTATION_PATTERN_ADOPTED`
- License: `Apache-2.0`
- Inspected revision: `708ebf9b8acf8ced0e0bfb2a6e19b4be76c9defc`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine deterministic orchestration, signed-lineage, and audit/evidence patterns; do not delegate canonical state.
- Integration paths: `src/project_pipeline/orchestration/persistence.py, src/project_pipeline/orchestration/recovery.py, tests/test_orchestration_recovery.py`
- Review: [`provenance/reviews/UPSTREAM-095_orchestration_pattern_review.md`](reviews/UPSTREAM-095_orchestration_pattern_review.md)

### UPSTREAM-100 — step-security/harden-runner

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `IMPLEMENTATION_PATTERN_ADOPTED`
- License: `Apache-2.0`
- Inspected revision: `05e31511f85b41b11d1cf0ef85d0992719546e2c`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Harden-Runner for GitHub Actions egress/audit hardening.
- Integration paths: `.github/workflows/quality.yml, src/project_pipeline/security/supply_chain.py, tests/test_security_supply_chain.py`
- Review: [`provenance/reviews/UPSTREAM-100_security_review.md`](reviews/UPSTREAM-100_security_review.md)

### UPSTREAM-102 — SWE-agent/SWE-ReX

- Disposition: `ADAPT_COMPONENT`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `5c995c365dfb1fd5bc56fda688be5d8538f9931f`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Prioritize SWE-ReX as the sandboxed local/remote worker execution adapter because it separates agent logic from infrastructure.
- Integration paths: `src/project_pipeline/upstream_integrations/swerex.py`
- Review: [`provenance/reviews/UPSTREAM-102_source_level_candidate.md`](reviews/UPSTREAM-102_source_level_candidate.md)

### UPSTREAM-103 — tauri-apps/plugins-workspace

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `OPTIONAL_ADAPTER_IMPLEMENTED`
- License: `MIT OR Apache-2.0`
- Inspected revision: `db9c5998feff9384f9cbbefcbe0d45937c00a1fc`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Windows desktop OS integration surface.
- Integration paths: `apps/desktop_shell/src-tauri/Cargo.toml, apps/desktop_shell/src-tauri/src/main.rs, apps/desktop_shell/src-tauri/tauri.conf.json, apps/desktop_shell/src-tauri/capabilities/main.json, apps/command_center/src/desktopBridge.mjs`
- Review: [`provenance/reviews/PASS-21_director_incident_notifications_upstream_review.md`](reviews/PASS-21_director_incident_notifications_upstream_review.md)

### UPSTREAM-104 — temporalio/temporal

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `NOT_SELECTED`
- License: `MIT`
- Inspected revision: `55cf6be564be2eb39e23fd6fa28a7ca6e59dcfa0`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualified separate-platform durable execution fallback and architecture reference.
- Integration paths: `none`
- Review: [`provenance/reviews/UPSTREAM-104.md`](reviews/UPSTREAM-104.md)

### UPSTREAM-105 — testcontainers/testcontainers-python

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `SELECTED_NOT_ACTIVATED`
- License: `Apache-2.0`
- Inspected revision: `f7d3887fe7c78e0b3a8b6eae82e105a4d3e0bca0`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Real transient dependency integration fixtures.
- Integration paths: `none`
- Review: [`provenance/reviews/UPSTREAM-105.md`](reviews/UPSTREAM-105.md)

### UPSTREAM-106 — treeverse/dvc

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `ARCHITECTURE_PATTERN_ADOPTED`
- License: `Apache-2.0`
- Inspected revision: `treeverse/dvc@metadata-snapshot-20260815T233400Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine data/artifact versioning concepts; Project Pipeline content-addressed artifacts and Git provenance remain canonical.
- Integration paths: `src/project_pipeline/domain/lifecycle.py, src/project_pipeline/lifecycle/environments.py, src/project_pipeline/lifecycle/retention.py, tests/test_pass22_platform_lifecycle.py`
- Review: [`provenance/reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md`](reviews/PASS-22_advanced_platform_lifecycle_upstream_review.md)

### UPSTREAM-108 — UKGovernmentBEIS/inspect_ai

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `c07dff4f8c029d92e785bf4109f5ed43f582c880`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Inspect AI as a structured evaluation framework for model/tool qualification and assurance.
- Integration paths: `src/project_pipeline/upstream_integrations/evaluation.py`
- Review: [`provenance/reviews/PASS-15_verification_evaluation_upstream_review.md`](reviews/PASS-15_verification_evaluation_upstream_review.md)

### UPSTREAM-110 — usemozzie/mozzie

- Disposition: `MINE_ARCHITECTURE`
- Usage state: `NOT_SELECTED`
- License: `MIT`
- Inspected revision: `usemozzie/mozzie@metadata-snapshot-20260815T224500Z`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Mine local-first desktop orchestration, parallel-work visualization, and review/dependency UX patterns; do not depend on the archived repository.
- Integration paths: `none`
- Review: [`provenance/reviews/PASS-19_command_center_upstream_review.md`](reviews/PASS-19_command_center_upstream_review.md)

### UPSTREAM-111 — vercel-labs/agent-browser

- Disposition: `ADAPT_COMPONENT`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `Apache-2.0`
- Inspected revision: `548b159b30eef119ccf6846c8bc807d0eaa3f6f8`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Implement an optional agent-browser CLI adapter for fast agent browser workflows; Playwright remains the evidence authority.
- Integration paths: `src/project_pipeline/verification/external_tools.py`
- Review: [`provenance/reviews/PASS-15_verification_evaluation_upstream_review.md`](reviews/PASS-15_verification_evaluation_upstream_review.md)

### UPSTREAM-114 — winsw/winsw

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `SELECTED_NOT_ACTIVATED`
- License: `MIT`
- Inspected revision: `1d0ee4a91bad596d5e7e9c360f2b39ef54674674`
- Dependency activation eligible: `true`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Windows-native service supervision.
- Integration paths: `none`
- Review: [`provenance/reviews/UPSTREAM-114.md`](reviews/UPSTREAM-114.md)

### UPSTREAM-115 — yamadashy/repomix

- Disposition: `ADAPT_COMPONENT`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `e3b15a406ed78d8a463620a032a059ce911bfc0e`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Prioritize a Repomix CLI/MCP adapter for context packing, filtering, token-aware repository compression, and source minimization.
- Integration paths: `src/project_pipeline/upstream_integrations/context.py`
- Review: [`provenance/reviews/UPSTREAM-115_source_level_candidate.md`](reviews/UPSTREAM-115_source_level_candidate.md)

### UPSTREAM-116 — zizmorcore/zizmor

- Disposition: `ADOPT_DEPENDENCY`
- Usage state: `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- License: `MIT`
- Inspected revision: `3a46aaade8a6005c92e8f9dc43c34be560682022`
- Dependency activation eligible: `false`
- Bounded source adaptation approved: `false`
- Project Pipeline role: Qualify Zizmor for GitHub Actions static security analysis.
- Integration paths: `src/project_pipeline/upstream_integrations/security.py`
- Review: [`provenance/reviews/UPSTREAM-116_integration_review.md`](reviews/UPSTREAM-116_integration_review.md)

## Retrieval

Use `PYTHONPATH=src python -m project_pipeline upstream --root . --summary` for a machine-readable summary.
Use `--id`, `--repository`, `--disposition`, `--inspection-state`, `--subsystem`, or `--text` for focused retrieval.
