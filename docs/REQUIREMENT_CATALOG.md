# Requirement Catalog

## Purpose

The catalog converts the canonical project corpus into bounded, machine-readable requirements without losing provenance, chronology, unresolved choices, or implementation status. It is designed to answer both directions of the trace:

`source → requirement → plan → decision → Jira → implementation → test → evidence`

and:

`implementation, test, or Jira item → requirement → plan → source`.

## Current catalog

The current catalog contains:

- 351 atomic requirements across 18 domains;
- 1,109 canonical source sections with explicit dispositions;
- 32 open decisions;
- 15 source-evolution records;
- 62 glossary terms;
- complete requirement-to-plan and requirement-to-Jira mappings;
- explicit implementation, test, and evidence mappings where work has been performed.

A requirement marked `PLANNED_ONLY` is accepted but not represented as implemented. `PARTIALLY_IMPLEMENTED` and `IMPLEMENTED` must be supported by concrete paths, tests, and evidence identifiers.

## Atomic requirement records

The authoritative registry is `plans/_traceability/requirements.jsonl`. Each record contains:

- a stable requirement ID and domain;
- a normative statement, rationale, type, priority, and risk;
- authority and disposition classifications;
- exact `SRC-NNN:Lxxxxxx-Lxxxxxx` evidence ranges and source sequence;
- plan, section, ADR, open-decision, evolution, Jira, implementation, test, and evidence links;
- verification class, expectation, and acceptance summary;
- an accurate implementation state.

Indexes in `plans/_traceability/` support direct lookup by ID, domain, and source.

## Source-section disposition

`source_sections.jsonl` covers every canonical section from the supplied knowledge corpus. Each section has exactly one explicit disposition, such as:

- `REQUIREMENT_LINKED`
- `DESIGN_RATIONALE`
- `SUPPORTING_EXAMPLE`
- `UPSTREAM_RESEARCH_CONTEXT`
- `USER_INTENT_CONTEXT`
- `OPEN_DECISION_CONTEXT`
- `DUPLICATE_SOURCE`
- `PREFIX_OVERLAP_SOURCE`

Known exact duplicates and exact-prefix sources are retained for provenance but are not counted as independent evidence. Validators check contiguous line coverage, exact source bounds, content digests, and the links from source sections to requirements, decisions, and evolution records.

## Decisions and source evolution

`open_decisions.jsonl` separates unresolved choices from accepted requirements. Each decision records options, constraints, the required resolution method, the decision gate, linked plans, linked requirements, and exact sources.

`source_evolution.jsonl` preserves chronology and records how later material refines, narrows, duplicates, supersedes, or conflicts with earlier material. Requirement records contain reverse links so a consumer can discover these relationships from either direction.

## Query examples

```bash
# Complete statistical summary
PYTHONPATH=src python -m project_pipeline requirements --root . --summary

# One requirement by stable ID
PYTHONPATH=src python -m project_pipeline requirements --root . --id REQ-ASSURE-0012

# High-priority security requirements
PYTHONPATH=src python -m project_pipeline requirements --root . --domain SEC --priority P0

# Requirements grounded in a canonical source
PYTHONPATH=src python -m project_pipeline requirements --root . --source SRC-017

# Text search within a bounded state
PYTHONPATH=src python -m project_pipeline requirements --root . --state PLANNED_ONLY --text idempotency
```

## Regeneration and validation

The machine-readable registries are authoritative. Regenerate human views and derived mappings after changing them:

```bash
PYTHONPATH=src python -m project_pipeline requirement-views --root .
PYTHONPATH=src python -m project_pipeline coverage --root .
PYTHONPATH=src python -m project_pipeline validate --root .
```

Validation rejects duplicate IDs, invalid or out-of-bounds source ranges, duplicate evidentiary identity, stale indexes, missing reverse links, unresolved plan/Jira/test/evidence references, source coverage gaps, and stale generated views.
