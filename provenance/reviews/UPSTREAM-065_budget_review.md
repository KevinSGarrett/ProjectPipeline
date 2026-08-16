# UPSTREAM-065 — MLflow Budget Governor pattern review

- Repository: `mlflow/mlflow`
- Inspected revision: `9355281ca38ff7e288161f0a71022400f8197175`
- License: Apache-2.0
- Source area: `docs/docs/genai/tracing/token-usage-cost/index.mdx`.

## Decision

Mine the implementation pattern of separately recording token usage and USD cost at operation/span scope and aggregating it to a higher-level trace. Missing model pricing remains unknown instead of being interpreted as free usage. Project Pipeline does not add MLflow as a dependency; its immutable budget ledger and OpenTelemetry bridge remain authoritative.
