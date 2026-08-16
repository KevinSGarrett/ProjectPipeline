# Scheduler Backpressure and Lease Recovery Runbook

## Purpose

Use this runbook when new work is unexpectedly not admitted, the scheduler enters brownout, or a worker disappears while holding resources.

## Diagnose

1. Run `project-pipeline scheduler status` and inspect current backpressure mode, latest plan, resource pools, and active leases.
2. Run `project-pipeline scheduler resources` to verify observed/configured capacity and control-plane reserve.
3. Run `project-pipeline scheduler leases` to identify active or expired ownership.
4. Re-run `project-pipeline scheduler plan` to obtain a read-only current admission decision and exclusion reasons.

## Backpressure response

Do not raise lane count simply to clear a queue. Confirm CPU, memory, disk, event lag, and concurrency pressure. Brownout intentionally stops optional new admission while preserving control-plane capacity. Correct the actual resource pressure or lower workload before returning to normal admission.

## Lost worker or stale lease

A disappeared worker's lease becomes non-authoritative after expiry. Do not manually reuse the old fencing token. Recompute the scheduler plan and acquire a fresh bundle for the recovering holder. The new lease receives a newer fencing token; operations carrying the old token must remain rejected.

## Forced intervention

Only release an active lease after confirming that its holder can no longer perform writes. Use the exact lease identifier and current fencing token with explicit apply and approval. Record the operational reason and re-evaluate the scheduler immediately afterward.

## Verification

After recovery, confirm that there is at most one active exclusive owner for every resource, bounded resource usage does not exceed available capacity, and a deterministic scheduler re-evaluation admits only conflict-safe work.
