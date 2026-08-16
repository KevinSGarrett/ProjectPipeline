# UPSTREAM-026 — dbos-inc/dbos-transact-py

- **Canonical URL:** `https://github.com/dbos-inc/dbos-transact-py`
- **Inspected revision:** `e0b742c2b9100676ea4b92cc71716e0b4ffa6108`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT`
- **Disposition:** `EVALUATE_LATER`
- **Dependency activation eligible:** `false`
- **Source incorporation approved:** `false`

## Project Pipeline role

Qualified durable-execution fallback used for conformance benchmarking against DurableExecutionPort; it is not the initial backend.

## Useful concepts

- library-based durable workflows
- PostgreSQL-backed queues
- workflow IDs and idempotency
- durable notifications and schedules

## Reviewed files and surfaces

- `README.md`
- `dbos package`
- `tests`
- `LICENSE`

## Integration boundary

- Implement WorkflowRuntime adapter.
- Use Testcontainers PostgreSQL for crash and idempotency tests.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

A library model reduces initial operational surface while retaining durable execution and recoverability.

## Risk and operability review

- **Security:** Workflow inputs, outputs, and error records require classification and redaction; database permissions must be least privilege.
- **Portability:** Python and PostgreSQL align with local and AWS profiles; deployment still requires supported database connectivity.
- **Maintenance:** Pin a qualified release and verify migrations and recovery behavior before production.
- **Maturity:** `ACTIVE_PRODUCTION_ORIENTED`
- **Compatibility:** `QUALIFIED_FALLBACK_NOT_ACTIVE`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Reviewed and retained as a qualified alternative or later-profile candidate; it is not selected for initial activation.

**Dependency implications:** No initial activation; re-review only when a documented profile or measured need justifies it.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/dbos-inc/dbos-transact-py`
- `https://docs.dbos.dev/python/`
- `https://github.com/dbos-inc/dbos-transact-py/blob/main/LICENSE`

## Project Pipeline disposition after source chronology review

- Source strategy: `QUALIFIED_FALLBACK_OR_LATER_PROFILE`
- Disposition: `EVALUATE_LATER`
- Dependency activation eligible: `false`
- Source incorporation approved: `false`
- Rationale: Reviewed and retained behind an internal port for a measured future trigger; it is not selected for initial activation and source incorporation is not approved.
