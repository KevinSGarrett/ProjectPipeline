# PLAN-ARCH-001 — Target System Architecture

- **Plan ID:** `PLAN-ARCH-001`
- **Status:** `ACTIVE`
- **Authority:** source-derived constraints plus accepted architecture decisions
- **Source basis:** `GOV-001:L000362-L000793`, `SRC-003:L000040-L000083`, `SRC-003:L000852-L001000`, `SRC-016:L001691-L001832`

## PLAN-ARCH-001:SEC-01 Architectural style

Project Pipeline uses a local-first modular control plane. Deterministic project authority, canonical state, policy enforcement, budget and resource admission, and completion remain inside one auditable boundary until measured scale or isolation evidence justifies extraction. Named responsibilities are modules and contracts, not automatic network services.

## PLAN-ARCH-001:SEC-02 Authority model

The Project Control Kernel owns admissible state transitions and recomputation. The Autonomy Director, model providers, optimizers, workflow backends, workers, Jira, GitHub, and user interfaces may recommend, execute, or project state only through typed commands and bounded authority. A backend success response is an observation until reconciliation and evidence gates accept it.

## PLAN-ARCH-001:SEC-03 Logical layers

The component model separates project definition, deterministic control, advisory intelligence, execution, platform services, integration, assurance, and operator experience. Dependency direction follows those boundaries. `architecture/component_catalog.json` is the machine-readable component authority.

## PLAN-ARCH-001:SEC-04 Canonical state and durability

PostgreSQL is the canonical transactional store. Commands, domain changes, idempotency records, inbox records, outbox records, leases, decisions, costs, incidents, and evidence metadata use one durable transaction boundary. Hatchet is the initial durable execution backend behind `DurableExecutionPort`; Temporal and DBOS remain qualified alternatives. Workflow history is not alternate project truth.

## PLAN-ARCH-001:SEC-05 Data and artifact ownership

Git owns repository revisions. PostgreSQL owns operational metadata and projections accepted by domain services. Immutable evidence, context packs, logs, reports, screenshots, recordings, and release artifacts use SHA-256 content identity with local filesystem and optional S3-compatible byte backends. Jira remains reconciled work-management state.

## PLAN-ARCH-001:SEC-06 Trust and policy boundaries

Operator input, advisory intelligence, worker execution, external systems, canonical state, and network access are distinct trust boundaries. Every crossing carries identity, intent, schema version, correlation, policy decision, timeout, and audit information; mutation also carries idempotency and reconciliation identity.

## PLAN-ARCH-001:SEC-07 Initial technology stack

The selected stack is recorded in `architecture/technology_stack.json` and ADR-0001 through ADR-0021. The baseline includes Python, PostgreSQL with pgvector, Hatchet behind an internal port, NetworkX, bounded OR-Tools optimization, FastAPI/Pydantic, React/Tauri/WinSW, OPA/Conftest, SOPS with age, OpenTelemetry/OpenLIT, Docker MCP Gateway, Pydantic AI, LiteLLM core, Playwright, Testcontainers, and Worktrunk. Activation remains evidence-gated.

## PLAN-ARCH-001:SEC-08 Replaceability and degraded operation

Every capability whose vendor or runtime may change is isolated behind an internal contract. Optional profile services must have a documented degraded mode. Replacement cannot weaken authority, provenance, policy, evidence, idempotency, or reconciliation semantics.

## PLAN-ARCH-001:SEC-09 Extraction criteria

A module may become an independently deployed service only when measured workload, security isolation, failure isolation, release cadence, or availability requirements justify the added consistency and operating burden. The extraction requires an ADR, compatibility tests, migration, rollback, and post-change evidence.

## PLAN-ARCH-001:SEC-10 Architecture assurance

Architecture registries, decisions, diagrams, plans, requirement mappings, and upstream dispositions are validated together. Stale summaries, unknown interfaces, duplicate state ownership, dangling component references, unreviewed selected dependencies, and contradictory backend selections fail repository validation.
