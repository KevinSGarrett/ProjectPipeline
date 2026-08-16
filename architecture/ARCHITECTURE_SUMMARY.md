# Target Architecture Summary

- Components: `35`
- Technology selections and qualified alternatives: `34`
- Trust boundaries: `6`
- Deployment profiles: `3`
- Canonical state owner: `PostgreSQL, with pgvector for semantic retrieval and content-addressed byte references for immutable artifacts`
- Initial durable execution backend: `Hatchet behind DurableExecutionPort; Temporal and DBOS are qualified fallbacks`
- Operator stack: `React and TypeScript web client with Tauri official plugins for Windows packaging and WinSW for eligible Windows-native services`

## Authority model

Project Pipeline separates deterministic authority from probabilistic advice. The Project Control Kernel, policy, budget, lease, and completion gates own admissible transitions; AI, provider, and optimization components may recommend or execute only within explicitly granted authority.

## Components by layer

### Advisory Intelligence

- `COMP-DIRECTOR-001` — **Autonomy Director**: Continuously propose priorities, plans, delegations, recovery actions, and escalations using live project state. (`PLANNED_ONLY`)
- `COMP-PROVIDER-001` — **Provider and Advisory Agent Gateway**: Expose typed advisory-agent and provider-neutral model interfaces with schema validation, fallback, cost telemetry, and circuit breaking. (`PARTIALLY_IMPLEMENTED`)
- `COMP-ROUTER-001` — **Capability Router**: Select qualified agents, models, providers, tools, and worker nodes by capability, performance, policy, budget, and availability. (`PARTIALLY_IMPLEMENTED`)

### Assurance

- `COMP-ASSURE-001` — **Verification Director and Completion Gate**: Compile objective verification criteria, derive affected-behavior test impact, execute the profile-driven verification portfolio and golden journeys, record browser/accessibility/performance/adversarial/property/mutation/fault/post-merge evidence, enforce loop/scope/review/evidence sufficiency controls, challenge lazy completion, localize failures, and authorize final completion only when all convergence questions pass. Broader security, resilience/DR, deployment, lifecycle, and Command Center obligations remain downstream and cannot be hidden by verification success. (`PARTIALLY_IMPLEMENTED`)
- `COMP-EVIDENCE-001` — **Evidence Ledger**: Record append-only evidence identities, claims, methods, freshness, results, provenance, and verification status. (`IMPLEMENTED`)

### Deterministic Control

- `COMP-BUDGET-001` — **Budget Governor**: Account for monetary spend, quotas, subscriptions, local compute, forecasts, spend leases, pressure modes, and cost per verified outcome. (`PARTIALLY_IMPLEMENTED`)
- `COMP-CTRL-001` — **Project Control Kernel**: Own canonical project state, admissible transitions, eligibility, dependency truth, assignment truth, and completion recomputation. (`PARTIALLY_IMPLEMENTED`)
- `COMP-GRAPH-001` — **Graph Analysis Service**: Represent dependency, conflict, ownership, and resource graphs and run deterministic graph algorithms. (`PARTIALLY_IMPLEMENTED`)
- `COMP-POLICY-001` — **Policy Engine**: Evaluate centralized testable runtime authority, action, egress, dependency, deployment, spend, and completion policies. (`PARTIALLY_IMPLEMENTED`)
- `COMP-RECOVERY-001` — **Recovery Director**: Detect incidents, select degraded modes and recovery plans, coordinate failover, preserve WIP, and verify restoration before normal operation resumes. (`PARTIALLY_IMPLEMENTED`)
- `COMP-RESOURCE-001` — **Resource Registry and Lease Manager**: Track machines, workers, files, worktrees, ports, environments, GPUs, credentials, and bounded fenced leases. (`PARTIALLY_IMPLEMENTED`)
- `COMP-SCHED-001` — **Dynamic Lane Scheduler**: Choose safe parallel work sets using conflict constraints, resource capacity, leases, backpressure, and optional optimization. (`PARTIALLY_IMPLEMENTED`)
- `COMP-SEQUENCE-001` — **Build Sequencer**: Maintain validated dependency DAGs, readiness, blockers, priority, critical path, and recomputation after change. (`IMPLEMENTED`)

### Execution

- `COMP-CONTEXT-001` — **Context Broker and Compiler**: Build immutable minimal context packs and receipts from trusted sources, repository maps, plans, acceptance criteria, and current state. (`PARTIALLY_IMPLEMENTED`)
- `COMP-LOCALMODEL-001` — **Local Model Gateway**: Register and select local advisory runtimes for offline/degraded assistance while preserving deterministic task and control semantics. (`PARTIALLY_IMPLEMENTED`)
- `COMP-WORKER-001` — **Worker Runtime and Node Harness**: Execute approved work in isolated workspaces, stream events, checkpoint progress, and report candidate results without self-declaring completion. (`PARTIALLY_IMPLEMENTED`)
- `COMP-WORKFLOW-001` — **Durable Workflow Runtime**: Persist and resume long-running workflow execution, timers, signal waits, retries, checkpoints, cancellation, worker heartbeats/fencing, uncertain-outcome reconciliation, and worker-loss recovery through a Project Pipeline-owned durable state model with Hatchet as the initial optional backend and DBOS/Temporal as qualified fallbacks. (`PARTIALLY_IMPLEMENTED`)

### Integration

- `COMP-JIRA-001` — **Jira Steward**: Maintain the structured local Jira model, synchronize authorized remote changes, reconcile divergence, and preserve source context. (`PARTIALLY_IMPLEMENTED`)
- `COMP-REPO-001` — **Repository Steward**: Own branch, worktree, pull-request, merge-gate, cleanup, WIP-preservation, and Git/GitHub reconciliation mechanics. (`PARTIALLY_IMPLEMENTED`)
- `COMP-TOOL-001` — **Tool Gateway**: Register, isolate, authorize, discover, invoke, and observe tools and MCP servers through a stable internal contract. (`PARTIALLY_IMPLEMENTED`)

### Operator Experience

- `COMP-API-001` — **Control API and Realtime Gateway**: Expose authenticated versioned HTTP, SSE, WebSocket, replay, Director-context, inbox, and typed-control contracts as non-authoritative operator projections. (`PARTIALLY_IMPLEMENTED`)
- `COMP-CHAT-001` — **Director Chat**: Provide grounded global/project/incident Director conversation, evidence-backed summaries, and confirmation-required typed action proposals; mutations remain exclusively on normal Control Kernel paths. (`IMPLEMENTED`)
- `COMP-NOTIFY-001` — **Notification Broker and Operator Inbox**: Deterministically prioritize, deduplicate, suppress, route, acknowledge, persist, retry, and audit operator notifications; Tauri local delivery and optional Apprise/ntfy remote adapters remain bounded behind the canonical broker and remote delivery is disabled by default. (`IMPLEMENTED`)
- `COMP-UI-001` — **Command Center**: Provide accessible Windows-capable and network-accessible views of project health, work, graph, evidence, budgets, providers, context, incidents, and controls. (`PARTIALLY_IMPLEMENTED`)

### Platform Services

- `COMP-ARTIFACT-001` — **Content-Addressed Artifact Store**: Store immutable artifact bytes by SHA-256 with PostgreSQL metadata, local filesystem baseline, reference-aware retention, and optional S3 backend. (`PARTIALLY_IMPLEMENTED`)
- `COMP-BACKUP-001` — **Backup and Restore Verification Controller**: Own domain recovery objectives, backup/restore plans, isolated restore verification status, and recovery evidence without equating backup existence with recovery readiness. (`PARTIALLY_IMPLEMENTED`)
- `COMP-CLOUDSPINE-001` — **Optional AWS Cloud Spine**: Provide optional witness, durable event transport, recovery storage, observability, budget controls, and bounded recovery/burst support while local control remains primary. (`PARTIALLY_IMPLEMENTED`)
- `COMP-DEPLOY-001` — **Runtime Supervisor and Deployment Profiles**: Install, configure, start, stop, monitor, qualify, upgrade, and roll back local Python, Windows-service/desktop, container, separated environment, and optional AWS runtime profiles while preserving explicit target qualification. (`PARTIALLY_IMPLEMENTED`)
- `COMP-LIFECYCLE-001` — **Platform Lifecycle and Portfolio Governor**: Govern multi-project allocation, multi-repository change coordination, environment and test-data lifecycle, contract evolution, retention/closure planning, version qualification, safe platform-release eligibility, and adoption maturity through deterministic non-destructive state machines. (`PARTIALLY_IMPLEMENTED`)
- `COMP-OBS-001` — **Observability and Health Service**: Correlate structured logs, metrics, traces, audit events, workflow, worker, model, context, cost, and health telemetry using OpenTelemetry conventions. (`PLANNED_ONLY`)
- `COMP-OUTBOX-001` — **Event, Inbox, and Outbox Service**: Commit domain events, external-write intents, inbound deduplication, retry state, and reconciliation records transactionally with canonical state. (`PLANNED_ONLY`)
- `COMP-PERSIST-001` — **Canonical Persistence**: Persist canonical project, work, requirement, traceability, transition, intake-compilation, bootstrap-receipt, integration-reconciliation, durable-workflow, event, wait, checkpoint, heartbeat, inbox/outbox, and recovery-decision state through PostgreSQL production ports and an executable SQLite local profile. (`PARTIALLY_IMPLEMENTED`)
- `COMP-SECRET-001` — **Secrets and Identity Broker**: Resolve secret references and issue least-privilege, task-scoped credentials without exposing secret material to prompts, logs, or source control. (`PARTIALLY_IMPLEMENTED`)

### Project Definition

- `COMP-INTAKE-001` — **Project Intake Compiler**: Inspect new or existing project roots without executing discovered code, compile deterministic project manifests, profiles, repository maps, authority inventories, and gap reports, then plan or apply bounded non-destructive bootstrap actions. (`PARTIALLY_IMPLEMENTED`)
- `COMP-TRACE-001` — **Requirement and Traceability Engine**: Maintain source-to-requirement-to-plan-to-work-to-code-to-test-to-evidence mappings with stable identifiers and exact provenance. (`IMPLEMENTED`)

## Technology decisions

- `TECH-AGENT-001` — **Pydantic AI**: Typed advisory agent adapter (`SELECTED`, `ADR-0016`)
- `TECH-API-001` — **FastAPI with Pydantic v2 contracts**: Typed HTTP and realtime application boundary (`SELECTED`, `ADR-0010`)
- `TECH-ARTIFACT-001` — **SHA-256 content-addressed local storage with optional S3-compatible adapter**: Immutable evidence and context bytes (`SELECTED`, `ADR-0013`)
- `TECH-BACKUP-001` — **pgBackRest**: PostgreSQL-specific backup and restore candidate (`PROFILE_OPTIONAL`, `ADR-0024`)
- `TECH-BACKUP-002` — **restic**: Portable encrypted repository and artifact backup candidate (`PROFILE_OPTIONAL`, `ADR-0024`)
- `TECH-DATA-001` — **PostgreSQL**: Canonical transactional state (`SELECTED`, `ADR-0007`)
- `TECH-DESKTOP-001` — **Tauri v2 official plugins**: Windows desktop shell and OS integration (`SELECTED`, `ADR-0011`)
- `TECH-EVENT-001` — **PostgreSQL transactional inbox and outbox records**: Recoverable domain-event delivery (`SELECTED`, `ADR-0007`)
- `TECH-GRAPH-001` — **NetworkX behind graph-domain services**: Authoritative graph analysis (`SELECTED`, `ADR-0009`)
- `TECH-LANG-001` — **Python 3.11 or newer**: Core implementation language (`SELECTED`, `ADR-0001`)
- `TECH-LOCALMODEL-001` — **Ollama local service candidate**: Default local advisory model service candidate (`PROFILE_OPTIONAL`, `ADR-0022`)
- `TECH-LOCALMODEL-002` — **llama.cpp server**: Direct local inference serving fallback (`QUALIFIED_FALLBACK`, `ADR-0022`)
- `TECH-LOCALMODEL-003` — **llama-swap**: Optional local multi-model hot-swap gateway (`PROFILE_OPTIONAL`, `ADR-0022`)
- `TECH-MODEL-GATEWAY-001` — **LiteLLM**: Replaceable multi-provider API model gateway (`ACTIVATION_BLOCKED`, `ADR-0016`)
- `TECH-OBS-001` — **OpenTelemetry and OTLP**: Portable telemetry contract (`SELECTED`, `ADR-0014`)
- `TECH-OBS-002` — **OpenLIT**: Agent and model instrumentation profile (`SELECTED`, `ADR-0014`)
- `TECH-POLICY-001` — **Open Policy Agent with Conftest preflight**: Runtime and configuration policy decisions (`SELECTED`, `ADR-0012`)
- `TECH-REPO-001` — **Worktrunk behind RepositoryWorkspacePort**: Git worktree lifecycle mechanics (`SELECTED`, `ADR-0020`)
- `TECH-SCHED-001` — **NetworkX**: Authoritative graph analysis (`SELECTED`, `ADR-0009`)
- `TECH-SCHED-002` — **Google OR-Tools**: Bounded lane and resource optimization (`SELECTED`, `ADR-0009`)
- `TECH-SECRET-001` — **SOPS with age recipients**: Encrypted repository-managed configuration (`SELECTED`, `ADR-0012`)
- `TECH-SECRET-002` — **OpenBao**: Optional dynamic secret broker (`PROFILE_OPTIONAL`, `ADR-0012`)
- `TECH-TEST-001` — **Playwright**: Browser acceptance and evidence (`SELECTED`, `ADR-0017`)
- `TECH-TEST-002` — **Testcontainers for Python**: Real dependency integration tests (`SELECTED`, `ADR-0017`)
- `TECH-TOOL-001` — **Docker MCP Gateway behind GovernedToolPort**: Initial MCP lifecycle and isolation gateway (`SELECTED`, `ADR-0015`)
- `TECH-TOOL-002` — **IBM MCP Context Forge**: Advanced MCP federation and gateway profile (`DEFERRED`, `ADR-0015`)
- `TECH-UI-001` — **React and TypeScript with an AG-UI compatibility adapter**: Network and desktop operator client (`SELECTED`, `ADR-0011`)
- `TECH-UI-PROTOCOL-001` — **AG-UI compatibility adapter**: Agent-to-operator event compatibility (`SELECTED`, `ADR-0011`)
- `TECH-VECTOR-001` — **PostgreSQL with pgvector**: Default semantic retrieval extension (`SELECTED`, `ADR-0018`)
- `TECH-VECTOR-002` — **Profile-gated and deferred until benchmark evidence**: Standalone semantic vector service (`DEFERRED`, `ADR-0021`)
- `TECH-WINDOWS-001` — **WinSW v3**: Windows-native service supervision (`SELECTED`, `ADR-0011`)
- `TECH-WORKFLOW-001` — **Hatchet**: Initial durable workflow implementation (`SELECTED`, `ADR-0008`)
- `TECH-WORKFLOW-002` — **Temporal**: Qualified durable-workflow fallback (`QUALIFIED_FALLBACK`, `ADR-0008`)
- `TECH-WORKFLOW-003` — **DBOS Transact Python**: Qualified PostgreSQL-centered durable-workflow fallback (`QUALIFIED_FALLBACK`, `ADR-0008`)

## Navigation

Use `PYTHONPATH=src python -m project_pipeline architecture --root . --summary` for the machine-readable summary.
Use `--component`, `--layer`, `--state`, and `--text` for bounded retrieval.
