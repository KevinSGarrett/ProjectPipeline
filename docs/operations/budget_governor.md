# Budget Governor Operations

Use `project_pipeline budget status` to inspect limits, active leases, ledger entries, forecasts, and blocking anomalies. Budget mutations require both `--apply` and `--approve`.

Configure a hard/soft/reserve hierarchy with `budget limit` and quota envelopes with `budget quota`. Evaluate work with `budget admit`, then persist an approved commitment with `budget reserve`. Settle the lease only from observed/reconciled evidence. If a provider may have executed but the response is lost, mark the lease `unknown`; do not release or repeat the paid operation until reconciliation proves the remote effect.

Use `budget forecast` for deterministic P50/P90/runway estimates, `budget metrics` for verified/merged-outcome efficiency, `budget anomaly` for runaway-cost classification, and `budget impact` before reducing a configured limit. `budget preflight` is read-only and refuses external Infracost execution unless `--allow-external-read` is explicit.

HARD_STOP does not mean stop the project. It means stop incremental paid work and continue with safe local/subscription/control/recovery/required verification paths where possible.
