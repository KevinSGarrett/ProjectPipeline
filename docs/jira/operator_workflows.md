# Jira operator workflows

All examples are run from the repository root with `PYTHONPATH=src`.

Validate and export the local mirror:

```bash
python -m project_pipeline jira validate --root .
python -m project_pipeline jira export --root . --output .local/exports/jira_mirror.json
```

Compare a portable bundle without modifying the repository:

```bash
python -m project_pipeline jira import-diff --root . \
  --input .local/exports/jira_mirror.json
```

Exercise the complete plan and outbox path against the deterministic mock:

```bash
python -m project_pipeline jira plan --root . --provider mock \
  --output .local/jira/reconciliation_plan.json
python -m project_pipeline jira sync --root . --provider mock
python -m project_pipeline jira status --root . --provider mock
```

`jira sync` is a dry run unless `--apply` is supplied. Application additionally requires `--approve` and `--authorization-id`. Live Atlassian application also requires runtime security mode `REQUIRE_APPROVAL` and valid reference-resolved Jira settings.

A meaningful comment can be prepared without a write:

```bash
python -m project_pipeline jira comment --root . --provider mock \
  --local-id PP-TASK-000001 --comment-kind VALIDATION_EVIDENCE \
  --comment-body "Validation evidence recorded: required contract tests passed."
```

See [`../../runbooks/jira_unknown_outcome_reconciliation.md`](../../runbooks/jira_unknown_outcome_reconciliation.md) before acting on an unknown outcome.
