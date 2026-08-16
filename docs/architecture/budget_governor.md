# Budget Governor

Project Pipeline owns deterministic budget authority. Provider gateways, observability platforms, cloud estimators, and billing APIs supply evidence only; they cannot approve spend or override the hard cap.

The control model separates cash, quota, subscription/local alternatives, and shadow cost. Cash uses integer USD microunits. Quota scarcity produces a routing signal but never becomes cash spend. Potentially billable work is admitted and then atomically reserved through a spend lease so concurrent stale decisions cannot collectively overshoot the current envelope.

A protected reserve is excluded from ordinary work. It is available only to explicit critical/recovery/security/deadline/required-verification reasons. Pressure progresses through GREEN, YELLOW, ORANGE, RED, and HARD_STOP. HARD_STOP blocks new incremental paid work while preserving local/subscription work and deterministic control/recovery paths.

Unknown pricing is `UNKNOWN`, not zero. Unknown remote outcomes retain their spend reservation until reconciliation. Cost history and forecasts are advisory evidence used by deterministic policy, with P50/P90 and confidence recorded separately from actual provider-reported or reconciled spend.

Upstream boundaries are recorded in `provenance/pass_14_budget_gate.json`: LiteLLM and OpenLIT are existing adapters, Infracost is a read-only preflight adapter, and Langfuse/MLflow provide architecture/implementation patterns. None owns Project Pipeline budget state.
