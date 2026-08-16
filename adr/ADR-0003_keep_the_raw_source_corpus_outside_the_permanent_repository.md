# ADR-0003 — Keep the raw source corpus outside the permanent repository

- **Status:** `ACCEPTED`
- **Source basis:** `GOV-001:L000123-L000183`, `GOV-001:L000225-L000287`
- **Date:** `2026-08-14`


## Context

The raw corpus is authoritative and must be preserved, but it contains session-cadence language prohibited by the permanent repository contract. Copying it into the project tree would make every release fail its own policy.

## Decision

Preserve the original archive byte-for-byte in the separate continuation package. Store only hashes, source metadata, duplicate relationships, and exact line references in the permanent repository.

## Alternatives considered

- Vendor the canonical corpus
- Keep raw sources in the continuation archive
- Publish the corpus as an external package

## Consequences

The project repository remains policy-compliant while full provenance is retained. Continuation requires both the project package and source-bearing continuation package.

## Review trigger

Revisit when measured project constraints, security findings, or operational evidence invalidate this decision.
