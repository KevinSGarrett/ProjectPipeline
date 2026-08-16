# Release, Handoff, and Cleanup

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-19` |
| Status | `ACTIVE` |
| Pack version | `1.0.0` |
| Primary domains | `release`, `post_merge` |
| Governing entry point | `AGENTS.md` |

## Release is an evidence-backed state

A version string or merged PR is not a release. Release requires a clean integrated `main`, accepted scope, applicable Completion Gate dimensions, test/evidence matrix, security and supply-chain checks, artifacts, installation, rollback, and post-release verification.

## Release readiness

Confirm:

- exact release SHA and version;
- all included Jira items and requirements;
- required tests and fresh evidence;
- no unresolved P0/P1 release blocker;
- dependency lock, license, notices, and vulnerability status;
- SBOM, integrity hashes, provenance/attestation as policy requires;
- reproducible artifact build;
- clean install/upgrade test on supported environment, including Windows-sensitive paths;
- backup/recovery and rollback procedure;
- release notes with known limitations and external activation status;
- authorization for public publication or deployment.

## Build and verify

Use deterministic archive/build tooling. Exclude `.git`, `.local`, caches, build debris, coverage files, local secrets, and nested archives. Verify root structure, member safety, duplicate names, CRC, prohibited terminology, secret scan, file manifest, and checksums.

## Publication

Publication is policy-gated. Verify exact repository/tag/release target and existing state before writing. If publication outcome is uncertain, stop and reconcile. Do not publish from an unverified exported snapshot as though it were a release branch.

## Post-release verification

Verify the actual published artifact and integrated SHA, installation, startup/smoke, critical journeys, external links/integrations where authorized, checksums, SBOM/provenance, and operator-visible status. Record environment and freshness. Roll back or block if release acceptance fails.

## Handoff

Use `templates/RELEASE_HANDOFF.md`. Include identity, SHA/version, scope, architecture decisions, active/blocked work, external systems, setup, verification, evidence, credentials by reference only, operations, recovery, known limitations, next priorities, and exact continuation route. No chat history is required.

## Branch and worktree cleanup

After integrated verification and Jira/evidence reconciliation, remove eligible worktrees and local branches, then remote branches when authorized. Preserve unmerged, dirty, or evidence-bearing work. Do not infer remote deletion from local absence.

## Test resource cleanup

Namespaced PPQS repositories, Jira projects, releases, and artifacts may persist for reproducibility. Remove only when ownership, retention, evidence, unknown outcomes, and reuse policy permit. Never remove canonical packs or comparison evidence.

## Final project completion

Only Completion Gate may declare complete project state. A final handoff must accurately label planned, partial, mock-verified, live-verified, externally blocked, and unknown items.
