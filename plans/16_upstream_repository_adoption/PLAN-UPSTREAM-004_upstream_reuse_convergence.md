# PLAN-UPSTREAM-004 — Upstream Reuse and Integration Convergence

- **Plan ID:** `PLAN-UPSTREAM-004`
- **Status:** `ACTIVE`
- **Authority:** governing upstream-research contract, canonical repository-reuse sources, and verified Project Pipeline implementation evidence
- **Source basis:** `GOV-001:L000797-L000876`, `GOV-001:L001219-L001285`, `SRC-011:L001212-L001345`, `SRC-016:L001691-L001832`, `SRC-016:L002197-L002303`

## PLAN-UPSTREAM-004:SEC-01 Upstream reuse is an implementation input

The supplied upstream catalog is an engineering input, not a passive bibliography. Before Project Pipeline implements a commodity capability, the responsible subsystem must identify applicable catalog candidates, inspect the highest-value source and test surfaces, record a disposition, and determine whether direct dependency use, an adapter, bounded adaptation, implementation-pattern mining, or explicit rejection produces the strongest result. Internal implementation without that check is an exception that requires a recorded reason.

## PLAN-UPSTREAM-004:SEC-02 Usage state is distinct from selection

`ADOPT_DEPENDENCY` and `ADAPT_COMPONENT` describe the architectural decision; they do not prove use. `provenance/upstream_usage.jsonl` records whether a selected repository is an active runtime dependency, an implemented optional adapter, an implemented external-CLI adapter, a bounded incorporated asset, or selected but not yet activated. Generated upstream reports must expose both disposition and actual usage state so catalog review cannot be mistaken for implementation.

## PLAN-UPSTREAM-004:SEC-03 Adapter-first dependency adoption

Mature upstream packages and executables remain behind Project Pipeline-owned ports. The upstream implementation may provide graph algorithms, optimization, worktree mechanics, model/provider abstraction, gateway lifecycle, telemetry instrumentation, testing, or other commodity capabilities. It may not become the authority for project state, policy, completion, evidence, routing intent, resource ownership, or irreversible external mutation. Version qualification, failure behavior, compatibility tests, and rollback remain Project Pipeline responsibilities.

## PLAN-UPSTREAM-004:SEC-04 Bounded source adaptation

Source copying remains denied by default. A bounded adaptation is permitted only when the repository license has been reviewed and a dedicated source-incorporation review records the exact repository, revision, source path, Project Pipeline path, content hash, notice path, adaptation type, and behavioral tests. Adapted assets must be small, purposeful, used by runtime or verification code, and independently reviewable. Wholesale vendoring is not implied by this policy.

## PLAN-UPSTREAM-004:SEC-05 Graph and optimization reuse

NetworkX is an active graph dependency behind Project Pipeline graph semantics. OR-Tools is implemented as an optional CP-SAT safe-set optimizer for larger scheduling candidate sets. Project Pipeline revalidates every optimizer result against its own conflict graph, resource capacity, and lane limits; an invalid or unavailable optimizer falls back deterministically. The optimizer therefore improves solution quality without owning scheduling authority.

## PLAN-UPSTREAM-004:SEC-06 Repository worktree reuse

Worktrunk is exposed through an optional fixed-argument CLI adapter for machine-readable worktree listing and bounded create/remove operations. The Repository Steward remains the approval and safety boundary. Mutating Worktrunk commands are dry-run by default, branch/base values are validated as data rather than shell fragments, and execution uses no shell. Native Git remains a fallback when Worktrunk is unavailable or unqualified.

## PLAN-UPSTREAM-004:SEC-07 Agent, provider, and tool reuse

Pydantic AI is implemented as an optional typed advisory-agent adapter without leaking framework types into the universal execution contract. LiteLLM is implemented as an optional stable OpenAI-compatible proxy adapter using only the MIT-licensed non-enterprise boundary; Project Pipeline retains capability-first routing, circuit breakers, provider health, qualification, and policy authority. Docker MCP Gateway is implemented as an optional tool-gateway command adapter using reviewed secure defaults and explicit server/tool allowlists. Provider or gateway availability never changes deterministic project intent.

## PLAN-UPSTREAM-004:SEC-08 Observability reuse

OpenLIT is implemented as an optional instrumentation bridge on top of the existing OpenTelemetry contract. Installation absence is reported as unavailable rather than simulated. Initialization can forward an explicitly configured OTLP endpoint and headers, while Project Pipeline remains responsible for redaction, correlation, evidence, and authoritative state. OpenLIT instrumentation is telemetry, not decision authority.

## PLAN-UPSTREAM-004:SEC-09 Future subsystem reuse gate

Every new subsystem must inspect relevant catalog candidates before substantial commodity implementation begins. A selected upstream must gain an actual usage-ledger record and concrete integration path before the project may represent it as integrated. Remaining catalog entries require systematic classification, with source-level review prioritized for repositories relevant to the next scheduled subsystem. Future work must not silently revert to rebuilding mature capabilities merely because an internal implementation is convenient.

## PLAN-UPSTREAM-004:SEC-10 Verification and provenance

Repository validation checks selected upstream usage records, bounded source-adaptation approvals, adapted-file hashes, notices, integration paths, and generated summary freshness. Behavioral tests verify optional adapters without claiming unavailable packages, credentials, paid-provider access, or live external success. Upstream source revisions and Project Pipeline integration evidence are retained so future replacement, upgrade, or removal is deliberate and reversible.
