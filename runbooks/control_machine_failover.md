# Control Machine Failover Runbook

## Prerequisites
1. Confirm canonical state backup/replication is readable.
2. Confirm the active control machine is unavailable or has relinquished authority.
3. Confirm the active authority lease is expired/fenced.
4. Obtain independent witness confirmation.
5. Confirm the standby machine is healthy and has the standby/recovery role.

## Approved actions
1. Freeze new authoritative commits on the failed node.
2. Capture recoverable WIP/checkpoint metadata.
3. Issue a strictly greater fencing token to the standby.
4. Restore or open canonical state.
5. Reconcile workflow, repository, Jira/GitHub outboxes, and uncertain outcomes.
6. Resume only work that remains eligible under current policy.
7. Notify the operator with old/new authority identities and evidence.

## Stop conditions
- Witness unavailable or contradictory.
- Active lease still valid.
- Two nodes claim the same or newer fencing token.
- Canonical state integrity cannot be verified.
- Required secret or policy material cannot be validated.

## Verification
- One and only one director can commit authority.
- Fencing token increased monotonically.
- Recovery reconciliation has no unresolved authoritative divergence.
- Durable workflows/checkpoints remain addressable.
