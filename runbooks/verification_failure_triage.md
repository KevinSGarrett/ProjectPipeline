# Verification Failure Triage

1. Identify the failed or blocked verification check ID and category.
2. Preserve stdout/stderr, screenshots, structured results, tool activation state, and source fingerprint.
3. Do not convert `BLOCKED`, `SKIPPED`, or unknown external results into passing evidence.
4. Determine whether the issue is implementation, fixture, environment, upstream-runtime availability, stale evidence, or verifier defect.
5. Route implementation defects to the owning work item; route verifier defects to the verification harness.
6. After a failure, the next attempt must introduce a new hypothesis, input, tool, environment, or recovery strategy where Loop Guard requires novelty.
7. Rerun the smallest affected verification set first, then the full cumulative suite and repository validator before completion.
8. If browser tooling is unavailable, record the capability as blocked; do not substitute an agent narrative for browser evidence.
9. Post-merge verification must run after generated evidence and manifests are finalized.
10. Recompute the Completion Gate; never override its failed later-pass obligations.
