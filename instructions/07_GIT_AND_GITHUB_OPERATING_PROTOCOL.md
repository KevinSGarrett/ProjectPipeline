# Git and GitHub Operating Protocol

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-07` |
| Status | `ACTIVE` |
| Pack version | `1.0.0` |
| Primary domains | `git`, `github` |
| Governing entry point | `AGENTS.md` |

## Governing model

`main` is the protected integrated codebase. Use short-lived work branches. A permanent development branch is not part of the default topology and may be introduced only by an accepted lifecycle decision that outweighs synchronization cost.

Repository/GitHub Steward owns safe Git invocation, branch/worktree governance, Branch Guardian, PR/check/review models, Merge Gate, and unknown-outcome reconciliation. Use it rather than improvised destructive shell sequences.

## Initial inspection

```bash
PYTHONPATH=src python -m project_pipeline repository inspect --root . --repository-root .
PYTHONPATH=src python -m project_pipeline repository branches --root . --repository-root .
PYTHONPATH=src python -m project_pipeline repository worktrees --root . --repository-root .
PYTHONPATH=src python -m project_pipeline repository guardian --root . --repository-root .

git status --short --branch
git branch -vv
git worktree list
git remote -v
```

If `.git` is absent, record snapshot limitation. Do not pretend the exported ZIP represents live branch or remote state.

## Dirty repository

Inspect and attribute every change. Preserve meaningful work through an owned commit, checkpoint branch, patch, or explicitly registered worktree as appropriate. Do not use hard reset, delete unknown untracked directories, remove dirty worktrees, or create another clone to escape state analysis.

Preserve first, inspect second, clean third.

## Commits

Commits are meaningful, reviewable, attributable, and reasonably atomic. Include the work identity where useful, for example `feat(scheduler): add capacity-aware admission [PP-TASK-000241]`. Do not commit every tiny edit or combine unrelated domains into one opaque commit. Generated output normally travels with its source change.

## GitHub pull requests

Before remote creation, verify exact repository, base, head, current head SHA, existing matching PR, intended reviewers, risk class, and external-write authority. Create one coherent PR, not one PR per file or subtask. Unknown creation outcome is reconciled by read, never blind retry.

## GitHub Issues and Jira

Jira remains the internal engineering backlog. GitHub Issues are suitable for public bug, feature, or community intake. When intake becomes engineering work, link/reconcile it into Jira rather than maintaining two independent implementations. Security reports are never public issues.

## Merge Gate

A merge requires the current evaluated head SHA, applicable status checks, required reviews and independent approval, resolved material conversations, accepted risk, rollback path, and no unresolved blocking defect. Never integrate around a failed required check.

Self-merge may be permitted by standing project authority only when all deterministic and independent gates are satisfied. AI authorship neither blocks nor relaxes the gate.

## Unknown GitHub outcome

For uncertain branch, PR, comment, label, ruleset, release, or merge effects:

```text
stop writes → read GitHub state → reconcile intended effect → retry only if absent and still authorized
```

## Cleanup

After successful merge and integrated-main verification, confirm no worktree owns the branch, no unpublished work remains, and the branch is merged. Remove eligible local worktrees and branches; delete remote branches only under policy. Local absence is not proof of remote deletion.

## Current remote activation state

Repository policy and workflow files are source-controlled here. Live branch rules, required checks, security features, and repository settings must be verified after the first `main` branch exists. Follow the activation checklist in `CREATION_REPORT.md`; do not claim settings are active from files alone.
