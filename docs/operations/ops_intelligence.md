# Operations intelligence

Observed health is calculated from persisted layer, worker, and cost records. It is
not a static label and is not a generated-only view.

Telemetry lives outside the subject Git tree at `.local/state/ops_intelligence/ops.sqlite3`.
Records are immutable. Conflicting replay of the same identifier fails closed.
Retention deletes expired rows and journals the cutoff.

Required layers: component, project, provider, synchronization, budget, and evidence.
A missing, stale, contradictory, mock-only-unverified, or failed observation cannot
produce a healthy overall score.

The CLI is `python -m project_pipeline ops-intelligence` with machine-readable JSON.
Command Center autonomy snapshots include these dimensions only when a store already
contains observations, so missing telemetry does not silently rewrite existing
autonomy health.
