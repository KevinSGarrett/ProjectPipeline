# Jira reconciliation

Reconciliation is deterministic and side-effect free until an approved plan is applied.

1. Validate and fingerprint the local mirror.
2. Read all remote pages into an immutable snapshot.
3. Match issues by managed local ID and then by recorded remote key.
4. Compare identity, type, parent, managed fields, labels, and normalized status.
5. Emit operations and conflicts with stable IDs.
6. Persist the snapshot, plan, and operation outbox.
7. Dry-run by default.
8. For approved application, persist `PENDING`, perform one operation, read back the result, then mark `APPLIED`.
9. Capture a post-write snapshot.
10. Stop and require reconciliation for any unknown outcome.

Conflict classes include duplicate remote mappings, local/remote divergence, remote-only issues, unmapped workflow status, hierarchy mismatch, stale observation, unknown write outcome, unsupported work type, and human decision required.

The local-authority profile pushes managed local fields and status to Jira. The collaborative profile can propose selected remote changes for local acceptance. Neither profile silently accepts remote completion when local acceptance, tests, review, blockers, or evidence remain incomplete.
