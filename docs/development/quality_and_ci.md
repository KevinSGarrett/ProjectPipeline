# Quality and CI

The quality contract combines:

- Python compilation;
- behavioral tests and coverage;
- deterministic dependency-state validation;
- generated-schema validation;
- repository self-validation;
- Ruff linting and formatting;
- strict Mypy checks for the new executable packages;
- package build;
- runtime dependency audit in CI.

Local environments without Ruff or Mypy receive an explicit unavailable result unless `--strict-tools` is requested. CI treats both tools as required.

```bash
PYTHONPATH=src python -m project_pipeline quality --root .
PYTHONPATH=src python -m project_pipeline quality --root . --strict-tools --coverage
```
