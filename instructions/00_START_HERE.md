# Start Here

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-00` |
| Status | `ACTIVE` |
| Pack version | `1.0.0` |
| Primary domains | `startup`, `project_identity` |
| Governing entry point | `AGENTS.md` |

## Mission

Enter the repository, recover canonical state from durable artifacts, choose eligible work, make a cohesive verified change, integrate it safely, and leave the repository easier for the next session to resume. The governing principle is to make real verified progress with the least coordination and infrastructure necessary to do the work correctly.

## Canonical identity

| Property | Canonical value |
|---|---|
| Project | `ProjectPipeline` |
| Stable project ID | `PROJECT-PIPELINE` |
| Repository | `https://github.com/KevinSGarrett/ProjectPipeline` |
| Default branch | `main` |
| Windows root | `C:\Project_X` |
| Instruction root | `C:\Project_X\instructions` |
| Jira project | `PP` |
| Jira site | `https://kevinsgarrett.atlassian.net` |

The package/import name `project-pipeline` and Python module `project_pipeline` remain valid technical identifiers. Older underscored repository/root metadata is legacy, not current authority.

## Cold-start sequence

1. Confirm the current directory is the repository root by locating `config/project.json`, `plans/PLAN_CATALOG.json`, `jira/BOARD_MANIFEST.json`, and this file.
2. Read `AGENTS.md`, this file, `01_AUTHORITY_AND_SOURCE_OF_TRUTH.md`, and `03_SESSION_BOOTSTRAP_AND_PREFLIGHT.md`.
3. Run the standard preflight and classify every failure before editing.
4. Determine whether this is a Git checkout or an exported snapshot. An exported snapshot has no valid branch/worktree/remote observation.
5. Inspect Project Control and Build Sequencer output; do not choose work by board order.
6. Route the selected task through `INSTRUCTION_COVERAGE_MATRIX.json` and `policies/CONTEXT_ROUTING.json`.
7. Confirm Definition of Ready, mutation authority, work ownership, worktree isolation, resource claims, risk tier, test strategy, and expected evidence.
8. Execute the autonomous cycle in `02_AUTONOMOUS_OPERATING_CONTRACT.md`.
9. Persist meaningful state outside chat before ending.

## Readiness decision

Proceed only when the work has a known owning item, accepted requirement or justified gap, acceptance boundary, satisfied dependencies or explicitly bounded blocker, applicable plan context, claimable resources, test strategy, and authority for intended writes. Administrative incompleteness does not block obvious safe work, but unknown behavior, ownership, or external authority does.

## Immediate hard stops

Stop the affected action when any of the following is true:

- an Oracle, hidden-evaluator, gold, or reference-solution path is encountered during PPQS work;
- a required credential is missing or appears exposed;
- a remote write outcome is unknown;
- a destructive operation would touch unpreserved work;
- a required gate failed;
- source authority is materially irreconcilable;
- the intended target or authorization is ambiguous;
- split-brain or stale-fencing risk exists;
- the action exceeds budget or policy.

Stopping one lane is not a reason to stop unrelated eligible work.

## Durable state sources

Use source control, `/jira`, the project-state database, evidence ledger, control snapshots, manifests, orchestration state, resource leases, and external reconciliation records. Do not use chat history as the record of truth. Use `.local/` only for appropriate mutable runtime state; do not commit noisy command-by-command logs.

## Task routing

- Jira or work selection: `05`, `06`
- Git, branches, worktrees, PRs: `07`, `08`, `09`
- implementation verification and completion: `12`
- PPQS: `13`
- upstream source or dependency: `14`
- secrets or external mutation: `15`
- parallel/remote worker: `10`, `16`
- repeated failure or restart: `11`, `17`
- human action: `18`
- release/handoff: `19`
- instruction change: `20`

Run `python scripts/instruction_cold_start.py --root .` to print this route without chat context.
