# PLAN-REQ-002 — Requirement Catalog Reconstruction and Source Coverage

- **Plan ID:** `PLAN-REQ-002`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000123-L000221`, `GOV-001:L001162-L001215`, `SRC-017:L000490-L000596`

## PLAN-REQ-002:SEC-01 Catalog model

The detailed catalog stores atomic obligations with stable identity, authority classification, exact source ranges, domain, priority, risk, disposition rationale, implementation state, plan and work mapping, verification expectations, decisions, and evolution relationships.

## PLAN-REQ-002:SEC-02 Source-section disposition

Every canonical source section is represented in `source_sections.jsonl`. A section either links to one or more requirements or records why it is contextual, illustrative, research-only, duplicated, overlapping, or decision-oriented. Section digests prove which exact normalized content was classified without copying the source corpus into the permanent repository.

## PLAN-REQ-002:SEC-03 Chronology and evolution

`source_evolution.jsonl` records duplicate, prefix, refinement, narrowing, concretization, and staged-adoption relationships. Later sources may revise recommendations while earlier evidence remains discoverable. Duplicate and prefix material does not increase evidentiary weight.

## PLAN-REQ-002:SEC-04 Terminology

`glossary.json` defines project terms, aliases, and source references so operators, implementers, and autonomous workers use consistent meanings across plans, work, code, tests, and evidence.

## PLAN-REQ-002:SEC-05 Open decisions

`open_decisions.jsonl` separates unresolved choices from accepted requirements. Each decision identifies its question, sources, options, constraints, resolution method, decision gate, affected plans, and status.

## PLAN-REQ-002:SEC-06 Validation and query interfaces

The repository validates source ranges, required fields, identifier links, source-section coverage, generated mappings, decisions, terminology, Jira indexes, tests, and evidence. The command-line interface supports deterministic catalog queries and summaries without loading the entire registry.

## PLAN-REQ-002:SEC-07 Jira decomposition

Detailed requirements are grouped into bounded capability stories beneath existing domain epics. Implementation tasks for catalog generation, validation, query tooling, Jira regeneration, and evidence are represented separately and may be completed only with current tests and evidence.
