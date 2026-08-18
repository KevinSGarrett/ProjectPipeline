---
name: github-branch-pr
description: Govern a ProjectPipeline branch, worktree, pull request, merge, and cleanup lifecycle.
---

# GitHub Branch and PR

1. Read instructions `07`, `08`, and `09`.
2. Inspect status, branch, worktrees, remotes, and existing PRs.
3. Preserve dirty work and register ownership; do not use an escape clone.
4. Use a policy-compliant work-item branch and isolated worktree with base SHA and resource claims.
5. Commit meaningful cohesive units and create/update one matching PR.
6. Complete the PR template, risk-tier checks, current-head Merge Gate, and any policy-qualified independent automated verification receipt.
7. Reconcile uncertain GitHub outcomes by read before retry.
8. Merge autonomously when the gate passes, verify integrated `main`, reconcile Jira/evidence, and remove eligible local/remote branches and worktrees in the same lifecycle. Never wait for a human GitHub approval.
