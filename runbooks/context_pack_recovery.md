# Context Pack Recovery Runbook

Use this runbook when a context pack is stale, incomplete, rejected, or cannot be reconciled with the current repository/project state.

1. Identify the `pack_id`, `delegation_id`, worker receipt, and the exact missing/stale/conflicting context keys.
2. Compare each candidate's `revision_id` with the delegation's expected revision and current authoritative source revision. Do not patch an immutable pack in place.
3. Resolve source truth first. If required context is unavailable or denied by policy, keep the affected delegation blocked while unrelated work remains eligible.
4. Recompile from a new or unchanged delegation envelope. A semantically unchanged input set should reproduce the same semantic pack identity; changed revisions or policy should produce a new pack.
5. If the firewall excluded content, correct the classification/authorization problem rather than weakening egress, trust, or secret policy silently.
6. Record a new receipt for the pack actually consumed. Preserve prior receipts as historical evidence.
7. For disconnected review, verify that diff, sources, tests, evidence, and rubric are all present before handing the package to a reviewer.
8. Never copy a raw credential into a context candidate to make compilation succeed. Resolve secrets only at the tool/provider boundary designed to use them.
