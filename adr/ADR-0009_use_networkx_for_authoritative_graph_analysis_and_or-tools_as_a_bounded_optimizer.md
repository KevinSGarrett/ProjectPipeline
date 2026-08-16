# ADR-0009 — Use NetworkX for authoritative graph analysis and OR-Tools as a bounded optimizer

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-016:L001752-L001756`, `SRC-016:L002215-L002224`
- **Date:** `2026-08-14`

## Context

Task readiness, dependency validity, critical paths, resource conflicts, and safe parallel sets are graph problems; capacity-aware scheduling can become a constrained optimization problem.

## Decision

Use NetworkX for deterministic dependency, conflict, ownership, and resource graph analysis. Add OR-Tools as a bounded optional optimizer for lane selection after the baseline safe-set algorithm exists. Every optimized schedule must be revalidated against canonical graph, policy, budget, and lease constraints before admission.

## Alternatives considered

- Let an LLM calculate task order and conflicts.
- Use OR-Tools as the sole source of dependency truth.
- Implement custom graph algorithms for commodity traversal and cycle detection.

## Consequences

Deterministic heuristics remain available when the optimizer is unavailable or exceeds its time budget. Optimization outputs are recommendations, not authority.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
