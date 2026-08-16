# Cold-Start Walkthrough

This example demonstrates a new session entering a normal Git checkout with no prior chat.

1. Locate root files and read `AGENTS.md`.
2. Run `python scripts/instruction_cold_start.py --root .`; confirm identity, first-read files, preflight commands, and stop conditions.
3. Read `instructions/00_START_HERE.md`, `01_AUTHORITY_AND_SOURCE_OF_TRUTH.md`, and `03_SESSION_BOOTSTRAP_AND_PREFLIGHT.md`.
4. Run doctor, repository validation, Jira validation, instruction validation, control evaluation, and control sequence.
5. Inspect `git status --short --branch`, branches, worktrees, and remotes.
6. Classify failures before edits. If `.git` is absent, record `SNAPSHOT_NOT_GIT_CHECKOUT` and continue file-level work.
7. Select the highest-value eligible non-epic item from Build Sequencer, not the first board row.
8. Load its issue, source-context packet, referenced requirements/plan sections, policies, affected code/tests, and evidence.
9. Confirm Definition of Ready and create a work/resource claim.
10. Use Repository Steward to create or reuse the branch/worktree, implement one cohesive slice, and test from targeted to risk tier.
11. Create/update one coherent PR, pass Merge Gate, verify integrated `main`, reconcile Jira/evidence, and clean eligible workspace state.
12. Persist a session checkpoint and select the next ready item.

The session never needs this example as authority; it is a demonstration of the governing files.
