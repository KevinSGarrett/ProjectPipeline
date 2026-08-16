# Jira unknown-outcome reconciliation

Use this runbook when a mutating Jira request was dispatched but no authoritative response was received.

1. Do not retry the operation with a new idempotency key.
2. Record and preserve the operation ID, plan ID, local ID, expected remote key/version, request fingerprint, correlation ID, provider error, and time.
3. Inspect `project-pipeline jira status` and confirm the operation is `UNKNOWN_OUTCOME`.
4. Capture a new remote snapshot using an authorized read-only connection.
5. Search by known remote key, managed `pp-local-id:*` label, summary, parent, and update time.
6. Compare observed remote semantics with the persisted operation payload.
7. When the effect exists, record or repair the local/remote mapping and mark the operation reconciled.
8. When the effect demonstrably does not exist, retry only through an explicitly approved reconciliation plan using the original semantic idempotency key.
9. When the result remains ambiguous, escalate for human resolution and keep automatic execution stopped.
10. Attach the new snapshot and reconciliation evidence to the incident and work item.

Never infer “not written” solely from a timeout, connection reset, gateway failure, or missing client response.
