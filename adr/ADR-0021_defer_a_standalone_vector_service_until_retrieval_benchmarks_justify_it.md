# ADR-0021 — Defer a standalone vector service until retrieval benchmarks justify it

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-011:L000601-L000652`, `SRC-016:L001777-L001780`
- **Date:** `2026-08-14`

## Context

Project Pipeline needs semantic retrieval with strong provenance, but a separate vector service would add credentials, backup, deployment, monitoring, and reconciliation burden to the local baseline.

## Decision

Use PostgreSQL plus pgvector for the default semantic profile while preserving exact identifiers, lexical retrieval, line-addressed sources, and deterministic filters. Defer Qdrant or another standalone vector service until benchmarked scale or retrieval requirements justify a separately operated capability. Permit sqlite-vec only in a constrained portable profile after compatibility validation.

## Alternatives considered

- Install a standalone vector database in every deployment.
- Use vector similarity as source authority or acceptance evidence.
- Omit semantic retrieval entirely.

## Consequences

The default profile has one fewer stateful service. Embedding model, version, chunk identity, source range, freshness, and index rebuild provenance remain mandatory. A future standalone service must implement the same retrieval port and pass compatibility tests.

## Review trigger

Revisit when measured corpus size, latency, filtering, replication, or availability requirements exceed the pgvector profile.
