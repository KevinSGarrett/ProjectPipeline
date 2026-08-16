# Repository Navigation

## Find why something exists

1. Locate the implementation file in `plans/_traceability/requirements_to_implementation.jsonl`.
2. Follow the requirement ID into `requirements.jsonl` or `requirements_by_id.json`.
3. Follow its exact source references, plan IDs, and plan-section IDs.
4. Follow its Jira IDs and acceptance criteria.
5. Follow test and evidence IDs to their registries.

## Find what implements a source requirement

1. Search `source_to_requirements.jsonl` for the exact source reference or query by source ID.
2. Follow each requirement through plan, work, implementation, test, and evidence mappings.
3. Consult `source_sections.jsonl` to see how nearby canonical source material was dispositioned.

```bash
PYTHONPATH=src python -m project_pipeline requirements --root . --source SRC-008
```

## Inspect unresolved choices and chronology

- `plans/01_requirements/open_decisions.jsonl` is the authoritative open-decision register.
- `plans/01_requirements/source_evolution.jsonl` preserves duplicate, prefix, refinement, and supersession relationships.
- `plans/01_requirements/OPEN_DECISIONS.md` and `SOURCE_EVOLUTION.md` are generated human views.

## Inspect Jira work

Use `jira/indexes/issues_by_id.json` for direct lookup, `jira/indexes/issues.jsonl` for streaming search, and `jira/source_context/<LOCAL-ID>.md` for a compact issue packet. Relationship truth is in `jira/relationships/graph.json`.

## Compact machine context

Start with `docs/generated/REPOSITORY_MAP.json`, `plans/PLAN_CATALOG.json`, `plans/_traceability/requirement_registry_summary.json`, and the targeted JSONL registries. Do not load every document when a stable ID, source range, or generated index is sufficient.
## Inspect or adopt a project repository

Use the intake commands to inspect a project root without executing repository content, then compile a deterministic manifest, repository map, profile set, and gap report. Bootstrap remains dry-run unless explicitly applied.

```bash
PYTHONPATH=src python -m project_pipeline intake inspect --target-root /path/to/project --mode EXISTING_PROJECT --project-name "Example Project"
PYTHONPATH=src python -m project_pipeline intake compile --root . --target-root /path/to/project --mode EXISTING_PROJECT --project-name "Example Project"
```

See `docs/intake/README.md` for the complete safety and operating contract.

