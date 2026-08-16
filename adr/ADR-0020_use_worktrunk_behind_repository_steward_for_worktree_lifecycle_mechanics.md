# ADR-0020 — Use Worktrunk behind Repository Steward for worktree lifecycle mechanics

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-016:L001765-L001766`, `SRC-016:L002181-L002191`, `SRC-016:L002237-L002240`
- **Date:** `2026-08-14`

## Context

Parallel workers require isolated workspaces, deterministic branch naming, cleanup, status, and protection against destructive worktree operations across Windows and Linux.

## Decision

Use Worktrunk for commodity worktree lifecycle mechanics behind a RepositoryWorkspacePort controlled by Repository Steward. Project Pipeline remains authoritative for assignment, resource ownership, branch policy, merge gates, and evidence. Native Git remains the compatibility fallback.

## Alternatives considered

- Let agents invoke arbitrary worktree commands without ownership checks.
- Copy Worktrunk internals into the repository.
- Make Worktrunk state the canonical assignment registry.

## Consequences

Worktrunk commands must execute through bounded subprocess adapters with dry-run, timeout, path validation, and audit. Repository Steward reconciles observed Git state after each operation.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
