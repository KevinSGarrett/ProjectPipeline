# ADR-0018 — Use PostgreSQL plus pgvector for semantic retrieval and profile-gate standalone vector services

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-011:L000601-L000652`, `SRC-016:L001777-L001780`, `SRC-016:L002201-L002203`
- **Date:** `2026-08-14`

## Context

Semantic retrieval is required, but a separate vector service would add state, backup, recovery, and operational complexity before scale evidence justifies it.

## Decision

Use PostgreSQL as the canonical store and enable pgvector for project semantic embeddings. Preserve exact source-address retrieval and deterministic metadata filters as the fallback and verification path. Keep Qdrant or another standalone vector service profile-gated until retrieval scale, latency, isolation, or availability measurements justify extraction.

## Alternatives considered

- Use exact retrieval only and omit semantic retrieval.
- Require a standalone vector database from the first implementation.
- Store semantic vectors in an untracked local sidecar.

## Consequences

The PostgreSQL extension, schema migrations, index strategy, backup/restore, embedding versioning, and retrieval-quality benchmarks become required activation evidence. A standalone vector service remains an explicit later decision rather than hidden infrastructure.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, source evolution, or measured workload characteristics invalidate its assumptions.
