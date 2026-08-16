# PLAN-CTX-002 — Context Broker, Compiler, and Delegation Implementation

- **Plan ID:** `PLAN-CTX-002`
- **Status:** `ACTIVE`
- **Authority:** source-derived Context requirements, deterministic Project Pipeline contracts, and the permanent Upstream Adoption Gate
- **Source basis:** `SRC-002:L000037-L000315`, `SRC-002:L000359-L000515`, `SRC-002:L000681-L001156`, `SRC-002:L001158-L001234`, `SRC-017:L000009-L000071`, `SRC-013:L000733-L000785`, `SRC-015:L000662-L000702`, `GOV-001:L000695-L000710`

## PLAN-CTX-002:SEC-01 Upstream-first implementation gate

Context implementation begins by loading the permanent upstream candidate set rather than rebuilding commodity capability blindly. Repomix remains the governed repository-packing adapter. MarkItDown is adopted as the optional lightweight document-normalization boundary; Docling Slim is adopted as the optional richer structured-document boundary. Serena contributes the symbol-first, progressively bounded retrieval pattern without receiving project authority. IBM MCP Context Forge contributes federation/resource/prompt/plugin boundary lessons while Docker MCP Gateway remains the selected initial Tool Gateway. Selection, integration, source incorporation, and live qualification remain distinct truth states.

## PLAN-CTX-002:SEC-02 Delegation envelope and authority contract

`DelegationEnvelope` is immutable and semantically identified. It carries objective, scope, exclusions, constraints, source references, expected outputs, acceptance criteria, authority scope, resource requirements, allowed tools, return protocol, required and optional context keys, and expected source revisions. Required and optional keys cannot overlap, and revision expectations cannot refer to undeclared context. A future dispatcher must require an envelope before agent work is admitted; Pass 12 implements the contract and compiler boundary but does not claim the Pass 13 durable dispatcher exists yet.

## PLAN-CTX-002:SEC-03 Context Broker minimality

The Context Broker selects only context explicitly requested by the delegation. Required keys are considered before optional keys, optional inclusion is bounded by policy, unknown keys are surfaced, and unrequested candidates are excluded. The policy favors symbol/summary/repository-map material before whole-file or whole-repository content and records omissions rather than silently expanding scope. This encodes the Serena/Repomix minimization lesson while preserving deterministic Project Pipeline semantics.

## PLAN-CTX-002:SEC-04 Context Compiler and immutable packs

The Context Compiler resolves selected candidates into immutable `ContextItem` records and a content-addressed `ContextPack`. Pack identity is derived from semantic content, delegation identity, policy version, revision-bearing items, coverage, omissions, redactions, warnings, and total size rather than wall-clock generation time. The pack is also written to the local content-addressed artifact store. The compiler fails closed when required coverage is below policy or the resulting pack exceeds the context-size boundary.

## PLAN-CTX-002:SEC-05 Trust, instruction authority, and Context Firewall

Instruction provenance is classified explicitly as governing, authoritative source-controlled, verified external evidence, untrusted repository material, or untrusted browser/external material. Only authority-bearing instruction/policy classes may act as instructions. The Context Firewall excludes secret-class material, enforces hosted-provider sensitivity limits, isolates untrusted instructions, optionally denies untrusted data, quarantines common prompt-injection markers as data, and redacts high-confidence secret-like values before pack construction.

## PLAN-CTX-002:SEC-06 Freshness, revision identity, and coverage

Every candidate carries a revision identity and observation timestamp. The compiler compares explicit expected revisions and age policy; stale required material is omitted and therefore fails required coverage, while stale optional material is either rejected or explicitly disclosed according to policy. Coverage is calculated against required delegation keys after freshness and firewall decisions, so selected-but-unusable context does not count as represented.

## PLAN-CTX-002:SEC-07 Receipts, reviewer packages, and telemetry

Workers return immutable context receipts identifying the pack consumed, worker, consumption state, omissions, conflicts, and additional requested context. A disconnected-review package can be emitted only when the pack contains a bounded diff, relevant sources, tests, evidence, and review rubric. Context telemetry exposes item and source counts, pack size, coverage score, trust distribution, stale count, redactions, omissions, and receipt status without recording raw secret values.

## PLAN-CTX-002:SEC-08 Persistence and migration

`PPDB-0009_context_delegation` adds reversible SQLite and PostgreSQL-oriented tables for delegation envelopes, immutable context packs, and receipts. Local persistence rejects identity collisions rather than overwriting immutable payloads. SQLite is behaviorally verified in this pass; PostgreSQL DDL remains implementation-complete but not live server-qualified.

## PLAN-CTX-002:SEC-09 CLI, schemas, document adapters, and operations

The CLI provides machine-readable context compile, status, pack retrieval, receipt, telemetry, and disconnected-review operations. Generated schemas cover delegation, candidate, policy, selection, firewall result, item, coverage, pack, receipt, telemetry, and reviewer-package contracts. MarkItDown and Docling integrations are optional and truthful when unavailable; neither package is auto-installed and neither receives context-authority decisions. Operator documentation and a context recovery runbook define stale-pack, receipt, and recompilation handling.

## PLAN-CTX-002:SEC-10 Verification and truth boundary

Pass 12 verification covers deterministic identities, broker minimality, context-size boundaries, revision staleness, trust classification, prompt-injection quarantine, secret redaction, provider egress, coverage failure, reviewer-package completeness, persistence/rollback, CLI behavior, and upstream adapter boundaries. The Context Broker/Compiler architecture component advances to `PARTIALLY_IMPLEMENTED`: local deterministic compilation is real, but durable dispatch admission, distributed worker consumption, live optional document runtimes, and full end-to-end orchestration remain later-pass work.
