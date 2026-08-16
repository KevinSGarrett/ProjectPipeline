# Local Jira Mirror

This directory is a structured local work-management representation optimized for autonomous retrieval and later remote synchronization. Individual JSON issue records are authoritative locally.

- `indexes/issues.jsonl` provides streaming access to all work items.
- `indexes/issues_by_id.json` provides direct lookup.
- `relationships/graph.json` and `relationships/issues.jsonl` provide deterministic parent and relationship edges.
- `source_context/` provides compact issue-specific source, plan, requirement, test, and evidence retrieval maps.
- `reports/backlog_status.json` records generated board counts and requirement coverage.

After changing an authoritative issue file, rebuild every derived index with:

```bash
PYTHONPATH=src python -m project_pipeline jira-rebuild --root .
```

Repository validation checks parent types, dependencies, acceptance criteria, plan ranges, source references, completion evidence, graph integrity, board counts, and requirement references.

No remote Jira board was inspected or changed in the current environment. Remote keys and observed versions remain null until authorized access exists.
