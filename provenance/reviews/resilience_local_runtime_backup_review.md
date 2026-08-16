# Resilience, Local Runtime, and Backup Upstream Review

- **Review date:** 2026-08-15
- **Scope:** local model runtime, constrained inference patterns, backup/restore tooling, and fault injection.
- **Authority rule:** upstream software may provide execution, serving, backup, restore, or fault-injection mechanics; Project Pipeline retains deterministic control, recovery, policy, budget, and completion authority.
- **Source incorporation:** no upstream source files were copied into Project Pipeline by this review.

## Local model runtime

- `UPSTREAM-040` (`ggml-org/llama.cpp`) — MIT. Use an optional adapter for a local OpenAI-compatible serving boundary. Live runtime qualification remains environment-specific.
- `UPSTREAM-058` (`kvcache-ai/ktransformers`) — Apache-2.0. Mine heterogeneous CPU/GPU and constrained-memory inference architecture; no direct dependency is selected.
- `UPSTREAM-068` (`mostlygeek/llama-swap`) — MIT. Use an optional gateway adapter for multi-model/hot-swap local routing when operational evidence justifies it.
- `UPSTREAM-072` (`ollama/ollama`) — MIT. Use as the initial local-service candidate behind the provider-neutral gateway. This resolves the previously unresolved catalog license metadata; live model/version qualification remains required.

## Backup and recovery

- `UPSTREAM-082` (`pgbackrest/pgbackrest`) — MIT. Select as the PostgreSQL-specific production backup/restore candidate. This resolves the previously unresolved catalog license metadata. A successful backup never establishes restore readiness.
- `UPSTREAM-090` (`restic/restic`) — BSD-2-Clause. Select as the portable encrypted repository/artifact backup candidate for local/offsite/S3-compatible profiles.
- `UPSTREAM-093` (`Shopify/toxiproxy`) — MIT. Retain the already implemented optional verification adapter and reuse it for isolated resilience/fault scenarios when the external runtime is installed.

## Integration boundaries

Project Pipeline implements only internal adapters, plans, validation, simulations, and discovery checks in the repository. No live external model, backup repository, PostgreSQL restore, Toxiproxy service, or cloud service is claimed as qualified by this source-only review. Activation requires pinned versions/revisions, security/provenance review, profile-specific compatibility evidence, and rollback/recovery proof.
