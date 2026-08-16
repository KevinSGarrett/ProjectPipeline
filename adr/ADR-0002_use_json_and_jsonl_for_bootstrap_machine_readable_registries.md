# ADR-0002 — Use JSON and JSONL for bootstrap machine-readable registries

- **Status:** `ACCEPTED`
- **Source basis:** `GOV-001:L001162-L001215`, `GOV-001:L001996-L002024`
- **Date:** `2026-08-14`


## Context

Requirements, relationships, and evidence need stable, streamable, language-neutral formats that autonomous workers can retrieve without loading large documents.

## Decision

Use JSON for bounded configuration and catalogs, and JSONL for potentially large appendable or streamable registries. Human explanation remains Markdown.

## Alternatives considered

- YAML-only registries
- Relational database immediately
- Prose-only records

## Consequences

Validation is portable and deterministic. A future database may become the operational store while these formats remain exchange and audit representations.

## Review trigger

Revisit when measured project constraints, security findings, or operational evidence invalidate this decision.
