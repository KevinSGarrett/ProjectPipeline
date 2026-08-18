# GitHub Steward closed-loop lifecycle

The Repository Steward owns local Git inspection, Branch Guardian safety,
immutable-head pull-request observation, Merge Gate, consolidation proof,
and cleanup. Live GitHub mutation remains deny-by-default and requires
`--apply --approve` plus an authorization identity.

## Autonomous review

When branch protection sets `required_approving_review_count` to `0`, Merge
Gate accepts a typed autonomous review receipt instead of a second human
GitHub approval. The receipt must bind:

- distinct implementer and reviewer identities
- distinct context fingerprints
- exact head and tree
- read-only reviewer authority
- zero unresolved blocking findings
- freshness within `max_age_seconds`

Self-review, same-context review, stale receipts, and head/tree drift fail
closed.

## Commands

Read-only:

```
python -m project_pipeline github status --root .
python -m project_pipeline github plan --root . --pull-number N --expected-head-sha SHA
python -m project_pipeline github protection-drift --root .
python -m project_pipeline github consolidate --root . --expected-head-sha SHA --component-head SHA
```

Guarded mutation — this is the only allowed merge path. The Cursor shell hook
denies `gh`/`hub`/`gh.exe` pull-request merge, `gh api` REST/GraphQL merge,
and `hub merge`, including forms that only pin `--match-head-commit`. A SHA
pin is not an autonomous receipt.

```
python -m project_pipeline github merge --root . --pull-number N --apply --approve --authorization-id AUTH --expected-head-sha SHA --review-receipt receipt.json
```

Recovery: persist the intent first, read back the remote effect, and treat
`UNKNOWN_OUTCOME` as reconciliation rather than a blind retry.
