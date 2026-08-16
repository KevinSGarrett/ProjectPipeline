# Context and Delegation

Project Pipeline treats context as a deterministic execution input, not as an unbounded prompt-building convenience. The Context Broker decides which declared keys may be considered for a delegation; the Context Compiler validates trust, freshness, data-egress policy, coverage, and size before emitting an immutable content-addressed pack.

## Authority boundary

The Context subsystem is authoritative for issued pack identity and receipt validation. It is not authoritative for project scope, Jira state, Git state, budgets, provider routing, or completion. Those remain owned by their established deterministic components.

A delegation envelope records the objective, scope, exclusions, constraints, source references, expected outputs, acceptance criteria, authority, resources, allowed tools, return protocol, requested context keys, and expected revisions. Pass 12 defines this contract; durable dispatch admission is intentionally deferred to the orchestration layer.

## Upstream adoption

The permanent Upstream Adoption Gate was executed before implementation. Repomix provides the external repository-packing boundary. MarkItDown and Docling Slim provide optional document-normalization boundaries. Serena's symbol-first and progressively shortened retrieval behavior is mined as an implementation pattern. IBM MCP Context Forge's separation of gateway resources, prompts and plugins is mined as an architecture pattern. Project Pipeline retains all trust, authority, freshness, coverage, egress, secret-handling, and pack-identity semantics.

The upstream-use incident and mandatory before/during/after checks remain part of every rehydration package. A later implementation pass must repeat the same subsystem-specific gate rather than relying on the fact that Pass 12 performed it once.

## Trust and firewall

Repository and external/browser content may be useful evidence but cannot become governing instructions by placement in a pack. Secret-class candidates are excluded. Hosted-provider egress is constrained by sensitivity policy. Prompt-injection-like text from untrusted sources is explicitly marked as data. High-confidence secret-like values are redacted before a pack is persisted or supplied to a worker.

## Freshness and coverage

Candidates carry revision identifiers and observation timestamps. Explicit revision mismatches and age policy make material stale. Required stale or denied items do not count toward coverage. Compilation fails closed below the required coverage threshold, preventing a worker from receiving an apparently complete pack whose critical source was actually unusable.

## Persistence and observability

`PPDB-0009_context_delegation` persists delegation envelopes, packs, and receipts. Packs are also placed in the local content-addressed artifact store. Telemetry contains counts and classification metadata rather than raw secret-bearing source text.
