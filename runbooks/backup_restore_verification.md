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

## Isolation and target safety
1. Configure an explicit absolute restore-root allowlist that is not a drive root, UNC/share, repository, workspace, or protected system path.
2. Resolve the candidate target, including Windows case normalization, then reject traversal, relative paths, and any symlink/junction/reparse escape.
3. Record a durable restore intent and idempotency identity before any copy.
4. Run plan/dry-run first. Destructive apply requires explicit approval and never targets project paths.
5. Verify the restored tree against the executable integrity manifest (path, size, SHA-256). Missing, extra, and corrupt members fail closed and are distinct from backup status.

## Rollback and interrupted recovery
1. Treat backup, restore, and verify as distinct durable states.
2. If apply is interrupted or the outcome is unknown, stop, read the intent and target, and reconcile before retry.
3. Identical idempotent replay returns the existing intent; conflicting input under the same key fails closed.
4. Keep the last valid recovery point. Do not promote a failed or unverified restore.
5. Destroy only disposable isolated targets after evidence capture.

## Stop conditions
- Restore target resolves to an active/production path.
- Credentials are not scoped to the backup/restore operation.
- Integrity validation fails.
- Observed RPO/RTO exceeds policy without an explicit recorded exception.
- Retention cleanup would delete the sole valid recovery point.
