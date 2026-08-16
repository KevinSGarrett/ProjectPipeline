# Release and Continuation Handoff

## Identity

- Project: `ProjectPipeline`
- Project ID: `PROJECT-PIPELINE`
- Repository: `KevinSGarrett/ProjectPipeline`
- Release version/tag: `[version]`
- Integrated SHA: `[sha]`
- Artifact digests: `[digests]`

## Included scope

- Jira items: `[IDs]`
- Requirements/plans/ADRs: `[IDs]`
- User/operator changes: `[summary]`

## Verification

- CI and security tiers: `[results]`
- End-to-end/PPQS: `[results and scope]`
- Installation/upgrade: `[environment and result]`
- Backup/restore/rollback: `[result]`
- SBOM/provenance/attestation: `[paths]`
- Post-release checks: `[result]`

## Current state

- Live verified: `[items]`
- Mock verified: `[items]`
- Partial/planned: `[items]`
- Blocked external: `[items and exact activation]`
- Unknown: `[items]`

## Operations

- Startup/shutdown: `[commands]`
- Observability: `[locations]`
- Recovery: `[runbooks]`
- Secrets: `[references only]`
- External systems: `[health and reconciliation state]`

## Active and next work

- Active branches/worktrees/PRs: `[identities]`
- Blockers/escalations: `[IDs]`
- Next eligible action: `[exact route]`

## Cold continuation

A new session reads `AGENTS.md`, runs `scripts/instruction_cold_start.py`, executes preflight, and resumes from `[checkpoint/state identity]` without chat history.
