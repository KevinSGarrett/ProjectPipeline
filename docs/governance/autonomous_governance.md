# Autonomous governance and product-definition controls

This slice makes instruction coverage, independent review, framework-version
drift, post-merge workspace/Jira classification, continuation freshness, archive
completeness, and the local-first product profile executable.

- `project-pipeline governance instruction-system`
- `project-pipeline governance review-director --review-receipt ...`
- `project-pipeline governance framework-version`
- `project-pipeline governance product-profile`
- `project-pipeline governance continuation-freshness`
- `project-pipeline repository post-merge-refresh`
- `project-pipeline archive` / `verify-archive`

Continuation packets bind the exact subject SHA/tree. A later integrated merge
makes a stored packet stale; the next autonomous action is rebuild, not a human
command. Review Director never implements the work it reviews.
`REQ-PDEF-0011` stays incomplete until the real 24-hour, 72-hour, release, and
Completion Gate receipts exist.
