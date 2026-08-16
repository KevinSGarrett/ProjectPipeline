# Release Upgrade and Rollback Runbook

## Authority boundary
A production Director or worker may prepare a candidate but may not independently certify, deploy, or promote its own replacement. Release promotion requires the existing Completion Gate, security/recovery evidence, and an authorized release actor.

## Upgrade sequence
1. Freeze the candidate identity, dependency/configuration/migration manifests, SBOM, provenance, and archive digest.
2. Create and verify a pre-migration backup. Restore it in an isolated location; backup creation alone is not recovery proof.
3. Run repository validation, functional regression, golden journeys, performance checks, security checks, and migration rollback checks against the candidate.
4. Run the candidate in synthetic certification and then shadow/no-write mode. Do not accept external writes during shadow certification.
5. Upgrade a standby/non-authoritative runtime first and verify protocol/schema compatibility with the current primary.
6. Perform a separately authorized controlled handoff only after certification evidence is accepted.
7. Observe health, error rate, reconciliation, queue/backlog state, resource/budget state, and Completion Gate facts during the defined observation window.
8. If any hard gate regresses, fence the candidate, restore the prior release and compatible state from the verified rollback material, then reconcile unknown outcomes before resuming work.

## Database migrations
Every migration requires pre-migration backup, recovery-copy rehearsal, forward validation, post-migration verification, and a tested down path. Schema contraction is prohibited while incompatible consumers remain.

## Current Pass 24 qualification
Local source and deterministic checks are qualified. Windows/WinSW, Docker, AWS/Terraform, and external scanner/signing runtimes are not available here and remain target-specific blockers rather than inferred successes.
