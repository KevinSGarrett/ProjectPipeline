# Budget Reconciliation Runbook

1. Identify the spend lease and preserve its idempotency key, provider/task identity, maximum authorized amount, and evidence references.
2. If the remote effect is uncertain, place the lease in `UNKNOWN_OUTCOME`. Do not retry the billable action and do not release the reservation merely because its normal TTL elapsed.
3. Query an authoritative provider/billing/operation record. If the effect occurred, create an immutable ledger entry from observed or provider-reported evidence and settle the lease. If the effect provably did not occur, use explicit no-effect reconciliation to release it.
4. If actual cost exceeds the lease maximum, record the full cost and retain the `OVERSPENT` result. Never truncate the ledger to the authorized amount.
5. Run anomaly detection when observed spend materially exceeds expected P90. A blocking anomaly must stop new paid work in the affected operational policy until reviewed.
6. Recompute status and forecast, then retain the evidence used for reconciliation. Do not edit old spend entries to change historical truth.
