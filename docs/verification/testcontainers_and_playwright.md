# Playwright and Testcontainers verification runtime

Playwright and Testcontainers are verification infrastructure. They produce evidence for the Completion Gate; they do not define completion.

## Playwright

`src/project_pipeline/verification/browser.py` is the governed Playwright adapter. `playwright_runtime_status()` reports:

- `MEASURED` only when the Playwright package and a Chromium-family executable are both present
- `UNAVAILABLE_IN_EXECUTION_ENVIRONMENT` when either is missing, with an explicit reason

The default CI lock does not install the `verification-browser` extra. Absence is an observed runtime fact, not a silent skip of a required check.

## Testcontainers / Docker engine

The Python `testcontainers` package is not part of the audited runtime set. Project Pipeline provisions the same class of transient dependency through the local Docker engine:

- `docker_engine_ready()` probes the CLI and engine without claiming a container ran
- `PostgresVectorContainer` starts `pgvector/pgvector:pg16`, records exact image identity, applies `PPDB-0025`, and removes the container on exit
- `tests/e2e/test_pgvector_container_recovery.py` kills and resumes the container, then reads persisted retrieval rows

Pass 23 still records the eight live-external legs, including a Testcontainers *Python package* mutation path, as `BLOCKED_EXTERNAL`. That is a different claim from this Docker-engine e2e proof.

## Cleanup

Every started container is removed in `finally`. Image pulls are tagged and identity-inspected; leftover `pp-c16-pgvector-*` names are force-removed on teardown.
