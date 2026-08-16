# Source Layout

The Python package uses a `src/` layout so an editable checkout does not accidentally import from the repository root.

- `configuration/` owns strict layered settings and secret references.
- `contracts/` owns versioned command, event, transition, diagnostic, and adapter-error models.
- `core/` owns deterministic command processing and the local idempotency journal.
- `observability/` owns correlation context, structured logging, redaction, and the OpenTelemetry provider boundary.
- `runtime/` composes diagnostics and the executable foundation smoke journey.
- existing planning, Jira, traceability, architecture, upstream, evidence, artifact, and validation modules retain their bounded responsibilities.

Runtime code must not import session-state materials. External providers remain behind ports, and no advisory model is authoritative for deterministic state transitions.
