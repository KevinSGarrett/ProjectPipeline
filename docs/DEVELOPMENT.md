# Development Guide

Project Pipeline requires Python 3.11 through 3.13, Git, and either PowerShell or a Bash-compatible shell. Start with [the repository engineering guide](development/README.md) and the platform-specific [setup instructions](development/setup.md).

The active runtime uses strict Pydantic contracts and an OpenTelemetry API/SDK foundation. Its exact observed dependency closure is committed under `requirements/`; the resolver-produced portable lock is tracked separately and must not be fabricated while package-index access is unavailable.

Core verification:

```bash
PYTHONPATH=src python -m project_pipeline doctor --root . --profile local
PYTHONPATH=src python -m project_pipeline dependencies validate --root .
PYTHONPATH=src python -m project_pipeline schemas check --root .
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m project_pipeline validate --root .
```

A behavior change updates the applicable requirement, plan, Jira item, implementation/test/evidence mappings, generated indexes, and manifests.
