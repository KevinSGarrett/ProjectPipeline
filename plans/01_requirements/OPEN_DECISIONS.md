# Open Decision Register

Decisions: `32`

## OPEN-DEC-0001 — Durable orchestration engine

**Status:** `RESOLVED`

**Resolved by:** `ADR-0008`

**Resolution:** Hatchet is the initial backend behind DurableExecutionPort; Temporal and DBOS remain qualified fallbacks. Live activation remains gated by recovery conformance tests.

Which durable workflow engine and deployment pattern best satisfy local Windows operation, restart recovery, observability, and optional AWS failover?

**Options**

- Hatchet
- Temporal
- DBOS-style internal workflow runtime
- Custom minimal durable state machine

**Constraints**

- Windows-compatible development
- Optional AWS
- No loss of unique control semantics

**Resolution method:** Implement representative recovery and cancellation prototypes, compare operational burden, then record an ADR.

**Decision gate:** Required before durable orchestration implementation is selected.

**Required by plans:** `PLAN-CTRL-001`, `PLAN-INFRA-001`

**Linked requirements:** `REQ-CTRL-0010`, `REQ-CTRL-0003`, `REQ-INFRA-0001`

**Sources:** `SRC-003:L000882-L000961`, `SRC-011:L000213-L000295`

## OPEN-DEC-0002 — Primary durable database

**Status:** `RESOLVED`

**Resolved by:** `ADR-0007`

**Resolution:** PostgreSQL is the canonical transactional store for domain, reconciliation, evidence metadata, and audit state.

Which database shall hold canonical project, workflow, evidence, audit, and reconciliation state?

**Options**

- PostgreSQL
- SQLite for local foundation with PostgreSQL migration
- Embedded transactional store plus external replication

**Constraints**

- Local-first
- Backup and restore
- Concurrency
- Migration safety

**Resolution method:** Benchmark representative state operations and recovery, define migration path, then record an ADR.

**Decision gate:** Required before persistent domain implementation.

**Required by plans:** `PLAN-ARCH-001`, `PLAN-INFRA-001`

**Linked requirements:** `REQ-ARCH-0008`, `REQ-ARCH-0007`, `REQ-INFRA-0002`

**Sources:** `SRC-006:L002748-L002819`, `SRC-017:L000281-L000359`

## OPEN-DEC-0003 — Command Center web and desktop stack

**Status:** `RESOLVED`

**Resolved by:** `ADR-0011`

**Resolution:** React is the network-accessible client, Tauri is the Windows shell, and WinSW supervises eligible native backend services.

Which UI and desktop packaging stack shall provide accessible real-time local and network operation?

**Options**

- React plus Tauri
- React web app with separate Windows service wrapper
- Alternative accessible desktop shell

**Constraints**

- Windows
- Network access
- Realtime
- Accessibility
- Maintainability

**Resolution method:** Build a state-streaming accessibility prototype and packaging spike, then record an ADR.

**Decision gate:** Required before Command Center implementation.

**Required by plans:** `PLAN-UX-001`

**Linked requirements:** `REQ-UX-0001`, `REQ-UX-0026`, `REQ-INFRA-0010`

**Sources:** `SRC-006:L001079-L001140`, `SRC-016:L000803-L000972`

## OPEN-DEC-0004 — Runtime policy and secrets backends

**Status:** `RESOLVED`

**Resolved by:** `ADR-0012`

**Resolution:** OPA and Conftest provide policy evaluation and tests; SOPS with age is the local encrypted configuration baseline; OpenBao is optional.

Which local-first policy and secret-storage backends shall be the initial supported defaults?

**Options**

- OPA plus SOPS/age
- Internal policy evaluator plus SOPS/age
- OPA plus OpenBao for multi-user deployment

**Constraints**

- Offline operation
- Recovery
- Least privilege
- Auditability

**Resolution method:** Threat model and prototype policy evaluation, secret rotation, recovery, and provider abstraction.

**Decision gate:** Required before live credential or policy enforcement.

**Required by plans:** `PLAN-SEC-001`

**Linked requirements:** `REQ-SEC-0009`, `REQ-SEC-0017`, `REQ-SEC-0010`

**Sources:** `SRC-009:L000007-L000009`, `SRC-016:L001057-L001176`

## OPEN-DEC-0005 — Remote Jira project configuration

**Status:** `BLOCKED_EXTERNAL`

What issue types, workflows, fields, permissions, and link types exist on the target remote Jira project?

**Options**

- Inspect actual target project after authorization

**Constraints**

- Read access required
- No remote mutation without authorization

**Resolution method:** Inspect actual Jira configuration only after access and explicit read authorization are available.

**Decision gate:** Required before live Jira synchronization.

**Required by plans:** `PLAN-GOV-001`

**Linked requirements:** `REQ-GOV-0008`, `REQ-GOV-0012`

**Sources:** `GOV-001:L000949-L001158`

## OPEN-DEC-0006 — Scheduler optimization approach

**Status:** `RESOLVED`

**Resolved by:** `ADR-0009`

**Resolution:** NetworkX owns deterministic graph analysis and OR-Tools is a bounded optimizer whose results are revalidated.

Should safe-set scheduling use deterministic heuristics alone or add OR-Tools optimization after the baseline graph model?

**Options**

- NetworkX plus deterministic heuristics
- NetworkX plus OR-Tools optimization

**Constraints**

- Explainability
- Fast recomputation
- Windows support

**Resolution method:** Run representative scheduling simulations and compare quality, determinism, complexity, and latency.

**Decision gate:** Required before optimizer dependency adoption.

**Required by plans:** `PLAN-SCHED-001`

**Linked requirements:** `REQ-SCHED-0009`, `REQ-SCHED-0010`, `REQ-SCHED-0017`

**Sources:** `SRC-016:L000037-L000220`, `SRC-014:L000378-L000748`

## OPEN-DEC-0007 — Event transport

**Status:** `RESOLVED`

**Resolved by:** `ADR-0007`

**Resolution:** Transactional inbox and outbox records are the baseline event transport; no external broker is mandatory for local operation.

Which transport shall carry durable local events and optional cloud ingress while preserving schema and idempotency?

**Options**

- Transactional database outbox
- Local message broker
- Database outbox plus optional cloud queue

**Constraints**

- Local-first
- Durability
- Low operational burden

**Resolution method:** Prototype event persistence, replay, and cloud ingress reconciliation.

**Decision gate:** Required before event-driven runtime implementation.

**Required by plans:** `PLAN-ARCH-001`, `PLAN-CTRL-001`

**Linked requirements:** `REQ-ARCH-0009`, `REQ-CTRL-0011`, `REQ-CTRL-0012`

**Sources:** `SRC-009:L000020-L000020`, `SRC-012:L000218-L000379`

## OPEN-DEC-0008 — Evidence and artifact metadata store

**Status:** `RESOLVED`

**Resolved by:** `ADR-0013`

**Resolution:** Artifact metadata is canonical in PostgreSQL and immutable bytes are referenced by SHA-256.

How shall artifact metadata, retention, verification, and references be persisted?

**Options**

- Primary database metadata
- Dedicated artifact catalog service

**Constraints**

- Content addressability
- Retention
- Integrity
- Searchability

**Resolution method:** Define canonical artifact schema and benchmark required queries.

**Decision gate:** Required before artifact service implementation.

**Required by plans:** `PLAN-ARCH-001`, `PLAN-ASSURE-001`

**Linked requirements:** `REQ-ARCH-0010`, `REQ-ASSURE-0002`, `REQ-ASSURE-0017`

**Sources:** `SRC-009:L000016-L000017`

## OPEN-DEC-0009 — Artifact byte backends

**Status:** `RESOLVED`

**Resolved by:** `ADR-0013`

**Resolution:** Local content-addressed filesystem storage is the baseline byte backend with optional S3-compatible storage.

Which local and cloud byte-storage backends shall be supported initially?

**Options**

- Filesystem plus S3
- Filesystem only initially
- Filesystem plus compatible object store

**Constraints**

- Digest integrity
- Large artifacts
- Backup
- Optional cloud

**Resolution method:** Implement backend contract and compare integrity, recovery, and operational cost.

**Decision gate:** Required before nonlocal artifact storage.

**Required by plans:** `PLAN-INFRA-001`

**Linked requirements:** `REQ-INFRA-0019`, `REQ-ARCH-0010`

**Sources:** `SRC-009:L000016-L000016`

## OPEN-DEC-0010 — MCP gateway implementation

**Status:** `RESOLVED`

**Resolved by:** `ADR-0015`

**Resolution:** Docker MCP Gateway is selected for the first implementation behind GovernedToolPort; Context Forge is deferred to a later federation profile.

Which MCP gateway or internal tool gateway shall enforce registration, policy, identity, and telemetry?

**Options**

- Docker MCP Gateway
- IBM MCP Context Forge
- Internal gateway using official protocol libraries

**Constraints**

- Windows
- Policy
- Isolation
- Protocol conformance

**Resolution method:** Run protocol and policy spikes against representative tools.

**Decision gate:** Required before broad live tool registration.

**Required by plans:** `PLAN-INFRA-001`, `PLAN-AGENT-001`

**Linked requirements:** `REQ-INFRA-0006`, `REQ-AGENT-0006`, `REQ-AGENT-0007`

**Sources:** `SRC-001:L000190-L000256`, `SRC-011:L000271-L000342`

## OPEN-DEC-0011 — Code intelligence backend

**Status:** `OPEN`

Which combination of parsers, language services, graph storage, and search shall power impact analysis?

**Options**

- Tree-sitter plus ast-grep plus internal graph
- Language-server integrations plus internal graph
- Hybrid with optional embeddings

**Constraints**

- Incremental updates
- Multiple languages
- Local operation

**Resolution method:** Benchmark symbol, caller, and test-impact accuracy on representative repositories.

**Decision gate:** Required before advanced impact analyzer.

**Required by plans:** `PLAN-OPS-001`, `PLAN-CTX-001`

**Linked requirements:** `REQ-OPS-0011`, `REQ-OPS-0012`, `REQ-CTX-0010`

**Sources:** `SRC-009:L000010-L000011`, `SRC-011:L000417-L000487`

## OPEN-DEC-0012 — Vector retrieval default

**Status:** `RESOLVED`

**Resolved by:** `ADR-0018`, `ADR-0021`

**Resolution:** PostgreSQL plus pgvector is the default semantic profile; standalone vector services remain profile-gated and benchmark-gated.

Should semantic retrieval be enabled by default, and which local vector backend should be used?

**Options**

- No vector dependency by default
- SQLite vector extension
- PostgreSQL pgvector
- Qdrant only for qualifying profiles

**Constraints**

- Token efficiency
- Operational burden
- Windows

**Resolution method:** Run a repository-context benchmark comparing lexical, structural, and vector retrieval.

**Decision gate:** Required before adding a default vector dependency.

**Required by plans:** `PLAN-CTX-001`, `PLAN-ARCH-001`

**Linked requirements:** `REQ-CTX-0009`, `REQ-CTX-0010`, `REQ-ARCH-0011`

**Sources:** `SRC-011:L000601-L000653`, `SRC-016:L001691-L001832`

## OPEN-DEC-0013 — GitHub live adapter

**Status:** `OPEN`

Should live GitHub operations use the official API client, official MCP server, or both behind one adapter?

**Options**

- REST/GraphQL adapter
- Official MCP adapter
- Dual adapter with conformance suite

**Constraints**

- Idempotency
- Audit
- Dry run
- Permissions

**Resolution method:** Compare operation coverage, permission boundaries, and reconciliation behavior.

**Decision gate:** Required before live GitHub writes.

**Required by plans:** `PLAN-GOV-001`

**Linked requirements:** `REQ-GOV-0024`, `REQ-GOV-0014`, `REQ-GOV-0019`

**Sources:** `SRC-011:L000389-L000416`, `SRC-016:L000710-L000802`

## OPEN-DEC-0014 — Jira live adapter

**Status:** `BLOCKED_EXTERNAL`

Should live Jira synchronization use Atlassian APIs, official MCP, or both behind one adapter?

**Options**

- REST adapter
- Official Atlassian MCP
- Dual adapter with conformance suite

**Constraints**

- Custom fields
- Workflow transitions
- Attachments
- Audit

**Resolution method:** Inspect target Jira configuration and test dry-run reconciliation.

**Decision gate:** Required before live Jira writes.

**Required by plans:** `PLAN-GOV-001`

**Linked requirements:** `REQ-GOV-0008`, `REQ-GOV-0012`, `REQ-GOV-0024`

**Sources:** `SRC-011:L000343-L000388`, `SRC-016:L000710-L000802`

## OPEN-DEC-0015 — Observability stack

**Status:** `RESOLVED`

**Resolved by:** `ADR-0014`

**Resolution:** OpenTelemetry and OTLP are the telemetry contract; OpenLIT is the selected agent/model instrumentation profile.

Which telemetry storage and analysis components shall be initial defaults?

**Options**

- OpenTelemetry plus local stores
- OpenLIT plus OpenTelemetry
- Optional Langfuse for qualifying deployments

**Constraints**

- Local-first
- Cost
- Model telemetry
- Standard export

**Resolution method:** Prototype end-to-end traces and compare deployment burden.

**Decision gate:** Required before production telemetry deployment.

**Required by plans:** `PLAN-OPS-001`

**Linked requirements:** `REQ-OPS-0001`, `REQ-OPS-0004`, `REQ-OPS-0009`

**Sources:** `SRC-011:L000721-L000792`, `SRC-016:L001285-L001472`

## OPEN-DEC-0016 — Local model runtime

**Status:** `RESOLVED`

**Resolved by:** `ADR-0022`

**Resolution:** Ollama is the initial local-service candidate behind the provider-neutral gateway; llama.cpp is the direct serving fallback and llama-swap is an optional multi-model/hot-swap layer. No model/runtime is production-qualified until pinned, benchmarked, and profile-verified.

Which local inference runtime shall serve CPU and GPU model capabilities?

**Options**

- Ollama
- llama.cpp server
- llama-swap over multiple runtimes

**Constraints**

- Windows
- CPU fallback
- GPU scheduling
- Model swapping

**Resolution method:** Benchmark startup, memory, throughput, tool calling, and failover.

**Decision gate:** Required before local model service implementation.

**Required by plans:** `PLAN-AGENT-001`, `PLAN-INFRA-001`

**Linked requirements:** `REQ-AGENT-0013`, `REQ-AGENT-0016`, `REQ-INFRA-0001`

**Sources:** `SRC-013:L001055-L001117`, `SRC-016:L001691-L001832`

## OPEN-DEC-0017 — Initial local model portfolio

**Status:** `OPEN`

Which qualified models shall provide lightweight planning, strong generalist, visual, and heavy review capabilities on available machines?

**Options**

- Qwen-family candidates
- Gemma-family candidates
- Other benchmark-qualified models

**Constraints**

- 32 GB RAM
- RTX 5060 VRAM
- License
- Quality

**Resolution method:** Run the local model benchmark suite on representative tasks.

**Decision gate:** Required before production routing to local models.

**Required by plans:** `PLAN-AGENT-001`

**Linked requirements:** `REQ-AGENT-0013`, `REQ-AGENT-0014`, `REQ-AGENT-0016`

**Sources:** `SRC-013:L000046-L000419`, `SRC-013:L000642-L000678`

## OPEN-DEC-0018 — Authentication for Command Center

**Status:** `OPEN`

Which authentication and authorization mechanism shall protect local and network-accessible operator surfaces?

**Options**

- Local OS identity plus session auth
- OIDC-capable local service
- Mutual TLS plus operator accounts

**Constraints**

- Windows
- LAN/Tailscale access
- RBAC
- Recovery

**Resolution method:** Threat model and prototype local plus remote login and recovery.

**Decision gate:** Required before network exposure.

**Required by plans:** `PLAN-SEC-001`, `PLAN-UX-001`

**Linked requirements:** `REQ-SEC-0005`, `REQ-SEC-0006`, `REQ-UX-0004`

**Sources:** `SRC-017:L000072-L000141`, `SRC-006:L001079-L001140`

## OPEN-DEC-0019 — AWS disaster-recovery topology

**Status:** `RESOLVED`

**Resolved by:** `ADR-0023`

**Resolution:** Use a local-primary hybrid AWS cloud spine: DynamoDB for authority witness, SQS for durable events, S3 for recovery/event storage, CloudWatch for observability, AWS Budgets for cost guardrails, Parameter Store for configuration references, and optional Lambda/notification/recovery control only when explicitly activated. Local deterministic control remains primary.

Which minimal AWS services shall provide witness, ingress, backup, notification, and optional DR control?

**Options**

- DynamoDB/SQS/S3 plus small EC2
- Serverless ingress plus on-demand EC2
- No DR director initially

**Constraints**

- Cost ceiling
- Optional AWS
- Secure IAM
- Recovery objectives

**Resolution method:** Model costs, failure modes, and recovery time; prototype only nonmutating infrastructure locally first.

**Decision gate:** Required before AWS IaC finalization.

**Required by plans:** `PLAN-INFRA-001`, `PLAN-RES-001`

**Linked requirements:** `REQ-INFRA-0012`, `REQ-RES-0024`, `REQ-INFRA-0013`

**Sources:** `SRC-012:L000001-L001056`

## OPEN-DEC-0020 — Policy language and evaluation runtime

**Status:** `RESOLVED`

**Resolved by:** `ADR-0012`

**Resolution:** Rego through OPA is the runtime policy language and engine; Conftest applies the same policy family to repository and infrastructure checks.

Should policy be expressed primarily in Rego/OPA or an internal typed policy model?

**Options**

- OPA/Rego
- Internal typed evaluator
- Hybrid with OPA for high-impact policy

**Constraints**

- Testability
- Explainability
- Local operation
- Upgrade safety

**Resolution method:** Implement representative may_merge, may_spend, and may_deploy policies and compare.

**Decision gate:** Required before production policy engine.

**Required by plans:** `PLAN-SEC-001`

**Linked requirements:** `REQ-SEC-0009`, `REQ-SEC-0016`, `REQ-SEC-0024`

**Sources:** `SRC-009:L000007-L000007`, `SRC-017:L000009-L000071`

## OPEN-DEC-0021 — Notification delivery channels

**Status:** `RESOLVED`

**Resolved by:** `ADR-0026`

**Resolution:** Use Tauri/Windows notifications for local delivery and Apprise as the initial optional remote fan-out adapter; retain ntfy as a separately qualified self-hosted target/adapter. Remote delivery remains disabled by default and Project Pipeline remains the canonical notification broker.

Which local and remote channels shall be supported initially by the notification broker?

**Options**

- Windows notifications plus ntfy
- Windows notifications plus Apprise
- Email or existing channels only

**Constraints**

- No new paid service
- Quiet hours
- Acknowledgement

**Resolution method:** Pass 21 focused upstream review plus bounded adapter, retry, deduplication, quiet-hours, action-link, failure-sanitization, and browser interaction tests.

**Decision gate:** Required before remote notification activation.

**Required by plans:** `PLAN-OPS-001`, `PLAN-UX-001`

**Linked requirements:** `REQ-OPS-0017`, `REQ-UX-0003`, `REQ-UX-0025`

**Sources:** `SRC-015:L000703-L000955`, `SRC-016:L000973-L001056`

## OPEN-DEC-0022 — Backup tooling

**Status:** `RESOLVED`

**Resolved by:** `ADR-0024`

**Resolution:** Use pgBackRest for PostgreSQL-specific backup/restore and restic for portable encrypted project/artifact/offsite backup. Backup success and restore verification remain separate states.

Which backup tools shall protect database, configuration, artifact metadata, and project-control state?

**Options**

- pgBackRest plus restic
- Native database backup plus restic
- Cloud snapshots plus local encrypted backup

**Constraints**

- Verified restore
- Encryption
- Local and optional cloud

**Resolution method:** Run destructive restore tests and measure RPO/RTO.

**Decision gate:** Required before production backup claim.

**Required by plans:** `PLAN-RES-001`, `PLAN-INFRA-001`

**Linked requirements:** `REQ-RES-0021`, `REQ-INFRA-0019`, `REQ-RES-0003`

**Sources:** `SRC-016:L001057-L001284`, `SRC-009:L000025-L000025`

## OPEN-DEC-0023 — Recovery objectives

**Status:** `RESOLVED`

**Resolved by:** `ADR-0025`

**Resolution:** Define profile defaults per persistent domain in config/resilience_policy.json: canonical state RPO 5m/RTO 30m; repository WIP RPO 15m/RTO 30m; evidence/operator history RPO 60m/RTO 60m; artifacts RPO 60m/RTO 120m. These are engineering targets and require measured recovery evidence before production-readiness claims.

What RPO and RTO values apply to canonical state, repository WIP, evidence, artifacts, and operator history?

**Options**

- Values defined per data domain and project profile

**Constraints**

- Cost
- Business impact
- Local hardware

**Resolution method:** Complete business impact analysis and recovery simulations.

**Decision gate:** Required before recovery readiness can be verified.

**Required by plans:** `PLAN-RES-001`

**Linked requirements:** `REQ-RES-0020`, `REQ-RES-0003`

**Sources:** `SRC-017:L000439-L000489`

## OPEN-DEC-0024 — Project profile catalog

**Status:** `OPEN`

Which project profiles and profile inheritance rules shall ship initially?

**Options**

- General software
- Web application
- Data/ML
- Infrastructure
- Content/media extensions

**Constraints**

- Avoid profile sprawl
- Universal core

**Resolution method:** Derive minimum profiles from representative target projects and common acceptance policies.

**Decision gate:** Required before profile-specific execution.

**Required by plans:** `PLAN-PDEF-001`

**Linked requirements:** `REQ-PDEF-0005`, `REQ-ARCH-0011`

**Sources:** `SRC-001:L001255-L001301`, `SRC-007:L000213-L000249`

## OPEN-DEC-0025 — License policy thresholds

**Status:** `RESOLVED`

**Resolved by:** `ADR-0019`

**Resolution:** The recorded license policy separates dependency eligibility from source incorporation and requires human legal review for prohibited or unclear classes.

Which licenses and dependency obligations are permitted automatically, require review, or are prohibited?

**Options**

- Organization-maintained allow/review/deny policy

**Constraints**

- Project distribution model
- Notice preservation
- Legal review boundaries

**Resolution method:** Create a policy matrix with legal review placeholders and test it against candidate repositories.

**Decision gate:** Required before source incorporation.

**Required by plans:** `PLAN-UPSTREAM-001`, `PLAN-SEC-001`

**Linked requirements:** `REQ-UPSTREAM-0002`, `REQ-UPSTREAM-0008`, `REQ-SEC-0021`

**Sources:** `SRC-017:L001065-L001121`, `GOV-001:L000831-L000876`

## OPEN-DEC-0026 — Worktree management implementation

**Status:** `RESOLVED`

**Resolved by:** `ADR-0020`

**Resolution:** Worktrunk supplies worktree mechanics behind Repository Steward with native Git fallback.

Should worktree operations use native Git commands, Worktrunk patterns, or another wrapper?

**Options**

- Native Git adapter
- Adapt Worktrunk patterns
- Evaluate Entire CLI for history preservation

**Constraints**

- Windows
- Recovery
- No hidden Git state

**Resolution method:** Prototype create, checkpoint, recover, merge, and cleanup flows.

**Decision gate:** Required before automated worktree mutation.

**Required by plans:** `PLAN-GOV-001`, `PLAN-SCHED-001`

**Linked requirements:** `REQ-GOV-0004`, `REQ-GOV-0016`, `REQ-SCHED-0012`

**Sources:** `SRC-010:L000259-L000298`, `SRC-011:L000885-L000911`

## OPEN-DEC-0027 — Environment and tool version manager

**Status:** `RESOLVED`

**Resolved by:** `ADR-0027`

**Resolution:** Project-native declarations and observed environment locks remain canonical; mise is optional for developer tool activation and Dev Containers are optional profile-specific reproducibility metadata.

Which tools shall provide reproducible language runtimes and locked environments?

**Options**

- mise plus language-native lock tools
- Project-native tools only
- Dev Containers where profile requires

**Constraints**

- Windows
- Offline cache
- Low burden

**Resolution method:** Pass 22 upstream/license/portability review plus existing Windows-first and offline constraints.

**Decision gate:** Required before environment contract finalization.

**Required by plans:** `PLAN-INFRA-001`

**Linked requirements:** `REQ-INFRA-0007`, `REQ-LIFE-0018`

**Sources:** `SRC-009:L000012-L000012`, `SRC-011:L000912-L000943`

## OPEN-DEC-0028 — Command Center interaction protocol

**Status:** `RESOLVED`

**Resolved by:** `ADR-0011`

**Resolution:** The internal realtime event model remains authoritative and exposes AG-UI only through a versioned compatibility adapter.

Should AG-UI or another event/action protocol be adopted between the UI and control APIs?

**Options**

- AG-UI
- Internal typed event API
- AG-UI-compatible internal model

**Constraints**

- Realtime
- Audit
- Replaceability

**Resolution method:** Prototype state streaming, approvals, and safe actions.

**Decision gate:** Required before frontend protocol commitment.

**Required by plans:** `PLAN-UX-001`, `PLAN-ARCH-001`

**Linked requirements:** `REQ-UX-0011`, `REQ-UX-0017`, `REQ-ARCH-0006`

**Sources:** `SRC-016:L000803-L000972`

## OPEN-DEC-0029 — Browser QA authority tools

**Status:** `RESOLVED`

**Resolved by:** `ADR-0017`

**Resolution:** Playwright is the authoritative browser acceptance and evidence tool; exploratory browser agents remain non-authoritative.

Which browser tools are authoritative for reproducible verification and which are exploratory only?

**Options**

- Playwright authoritative and browser agents exploratory
- Playwright plus Maestro for desktop/mobile profiles

**Constraints**

- Determinism
- Evidence
- Accessibility

**Resolution method:** Run representative golden journeys and compare reproducibility.

**Decision gate:** Required before browser QA stack selection.

**Required by plans:** `PLAN-ASSURE-001`, `PLAN-UX-001`

**Linked requirements:** `REQ-ASSURE-0025`, `REQ-CTX-0018`, `REQ-UX-0021`

**Sources:** `SRC-011:L000850-L000884`, `SRC-016:L001177-L001472`

## OPEN-DEC-0030 — Remote GitHub target configuration

**Status:** `BLOCKED_EXTERNAL`

What branch protections, required checks, permissions, environments, and repository settings exist on the target GitHub repository?

**Options**

- Inspect target repository after authorization

**Constraints**

- Read access required
- No write without authorization

**Resolution method:** Read target configuration and reconcile with local policy before any mutation.

**Decision gate:** Required before live GitHub synchronization.

**Required by plans:** `PLAN-GOV-001`

**Linked requirements:** `REQ-GOV-0019`, `REQ-GOV-0024`

**Sources:** `GOV-001:L002184-L002196`

## OPEN-DEC-0031 — External provider budget defaults

**Status:** `BLOCKED_EXTERNAL`

What monthly and per-project ceilings apply to APIs, cloud compute, and optional SaaS providers?

**Options**

- Operator-defined limits per provider and project profile

**Constraints**

- No spending without approval
- Reserve for critical work

**Resolution method:** User supplies ceilings before live billable execution; simulations use zero-spend defaults.

**Decision gate:** Required before live paid execution.

**Required by plans:** `PLAN-BUDGET-001`

**Linked requirements:** `REQ-BUDGET-0005`, `REQ-BUDGET-0007`, `REQ-BUDGET-0010`

**Sources:** `SRC-004:L000148-L000251`, `SRC-012:L000565-L000618`

## OPEN-DEC-0032 — Release signing identity

**Status:** `OPEN`

Which signing identity and trust root shall attest production release artifacts?

**Options**

- Sigstore keyless where supported
- Organization-managed signing key
- Unsigned local development artifacts only

**Constraints**

- Identity
- Recovery
- CI permissions
- Offline support

**Resolution method:** Define release environment and trust model, then test signing and verification.

**Decision gate:** Required before signed production releases.

**Required by plans:** `PLAN-SEC-001`, `PLAN-REL-001`

**Linked requirements:** `REQ-SEC-0008`, `REQ-SEC-0020`, `REQ-REL-0005`

**Sources:** `SRC-009:L000017-L000017`, `SRC-017:L000142-L000191`
