# Runtime Configuration

Configuration precedence is:

1. `config/runtime/base.json`
2. selected profile in `config/runtime/profiles/`
3. optional explicit JSON file
4. `.env` values and process environment
5. repeated CLI `--set key=value` overrides

Models reject unknown fields. Secret values are never stored in configuration; integrations accept only `env://NAME` or repository-confined `file://relative/path` references. Resolution occurs only when an adapter explicitly requests the secret.

```bash
PYTHONPATH=src python -m project_pipeline config validate --root . --profile local
PYTHONPATH=src python -m project_pipeline bootstrap --root . --profile local --prepare
```
