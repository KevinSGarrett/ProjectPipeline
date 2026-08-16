# Traceability Registries

These registries provide machine-readable links among source, requirement, plan, decision, work, implementation, tests, evidence, and completion state. JSONL is used for large registries so they can be streamed and searched without loading the complete project.

## Authoritative and derived records

- `requirements.jsonl` — authoritative atomic requirement catalog
- `source_sections.jsonl` — exhaustive disposition of all canonical source sections
- `source_to_requirements.jsonl` — canonical source range to requirement links
- `requirements_to_plans.jsonl` — requirement to plan and section links
- `requirements_to_decisions.jsonl` — requirement to accepted ADR links
- `requirements_to_open_decisions.jsonl` — requirement to unresolved decision links
- `requirements_to_evolution.jsonl` — requirement to chronology and source-evolution links
- `requirements_to_jira.jsonl` — requirement to local work-item links
- `requirements_to_implementation.jsonl` — requirement to code, configuration, and documentation links
- `requirements_to_tests.jsonl` — requirement to test identifiers
- `requirements_to_evidence.jsonl` — requirement to evidence identifiers
- `requirements_by_id.json` — direct requirement lookup
- `requirements_by_domain.json` and `requirements_by_source.json` — bounded retrieval indexes
- `requirement_registry_summary.json` — deterministic catalog counts
- `source_section_summary.json` — deterministic section-disposition counts
- `coverage_report.json` and `coverage_report.md` — implementation and traceability coverage

Generated human views are maintained in `plans/01_requirements/` and validated against their machine-readable sources.

## Retrieval

```bash
PYTHONPATH=src python -m project_pipeline requirements --root . --summary
PYTHONPATH=src python -m project_pipeline requirements --root . --domain CTRL --state PLANNED_ONLY
PYTHONPATH=src python -m project_pipeline requirements --root . --source SRC-014
PYTHONPATH=src python -m project_pipeline requirements --root . --text reconciliation
```

Use stable IDs and exact `SRC-NNN:Lxxxxxx-Lxxxxxx` ranges when passing context to an engineer or autonomous worker. Do not treat duplicate or prefix-overlap source records as independent confirmation.
