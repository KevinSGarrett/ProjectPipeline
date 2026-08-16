# Contracts and Schemas

Pydantic models define versioned command, result, event, transition, action-intent, diagnostic, secret-reference, runtime-configuration, and adapter-error contracts. Unknown fields are rejected and timestamps must be timezone-aware.

Generated Draft 2020-12 JSON Schemas live under `schemas/`. The repository validator compares committed files byte-for-structure with models so stale schemas fail validation.

```bash
PYTHONPATH=src python -m project_pipeline schemas write --root .
PYTHONPATH=src python -m project_pipeline schemas check --root .
```
