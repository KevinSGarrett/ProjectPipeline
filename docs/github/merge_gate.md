# Merge Gate Evaluation

Merge readiness is evaluated from a typed pull-request snapshot at a specific head SHA. Required status checks are matched by name. Completed checks with `success`, `neutral`, or `skipped` conclusions satisfy the local check predicate; failed, timed-out, cancelled, stale, action-required, startup-failed, absent, or incomplete required checks block readiness.

Reviews are reduced to the latest observed review per author. Any current `CHANGES_REQUESTED` decision blocks readiness, and the number of current approvals must meet policy. Branch protection can provide required checks and approval counts; explicit local policy can narrow or strengthen those requirements.

A merge operation carries the expected head SHA. The GitHub merge request sends that SHA so a changed pull-request head is rejected instead of silently merging a revision that was never evaluated.
