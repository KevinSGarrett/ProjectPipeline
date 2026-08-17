# Backup and Restore Verification Runbook

## Backup
1. Load the recovery objective for the data domain.
2. Resolve credentials through the credential/secret broker; never embed keys in commands or configuration.
3. Use pgBackRest for canonical PostgreSQL state and restic for general encrypted repository/artifact protection.
4. Record backup identity, domain, creation time, repository, and integrity digest where available.
5. Build a content-addressed integrity manifest containing path, SHA-256, and size for all backup-set members.
6. Mark backup status only for backup creation; never treat it as restore verification success.

## Restore verification
1. Provision an isolated target that cannot overwrite the active environment.
2. Restore the selected backup into that target.
3. Validate schema/migrations, row or object counts, integrity hashes, required authority records, and application startup/read paths.
4. Measure observed RPO and RTO against the configured objective.
5. Record a restore-verification record separately from backup status.
6. Destroy the isolated target only after evidence capture.
7. Verify idempotent retry behavior for interrupted and duplicate restore requests before declaring the runbook outcome stable.

## Mandatory failure scenarios
- Corrupt backup artifact
- Missing backup artifact
- Stale backup outside objective window
- Partial restore output
- Interrupted restore operation
- Duplicate restore request (idempotent replay)
- Insufficient local disk space
- Permission denied on target
- Locked-file collision on target
- Unknown restore outcome requiring reconcile-before-retry

## Stop conditions
- Restore target resolves to an active/production path.
- Credentials are not scoped to the backup/restore operation.
- Integrity validation fails.
- Observed RPO/RTO exceeds policy without an explicit recorded exception.
- Retention cleanup would delete the sole valid recovery point.
