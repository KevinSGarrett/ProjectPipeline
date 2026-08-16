# Backup and Restore Verification Runbook

## Backup
1. Load the recovery objective for the data domain.
2. Resolve credentials through the credential/secret broker; never embed keys in commands or configuration.
3. Use pgBackRest for canonical PostgreSQL state and restic for general encrypted repository/artifact protection.
4. Record backup identity, domain, creation time, repository, and integrity digest where available.

## Restore verification
1. Provision an isolated target that cannot overwrite the active environment.
2. Restore the selected backup into that target.
3. Validate schema/migrations, row or object counts, integrity hashes, required authority records, and application startup/read paths.
4. Measure observed RPO and RTO against the configured objective.
5. Record a restore-verification record separately from backup status.
6. Destroy the isolated target only after evidence capture.

## Stop conditions
- Restore target resolves to an active/production path.
- Credentials are not scoped to the backup/restore operation.
- Integrity validation fails.
- Observed RPO/RTO exceeds policy without an explicit recorded exception.
