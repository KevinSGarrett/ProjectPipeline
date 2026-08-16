---
name: failure-recovery
description: Recover a blocked, repeated-failure, restarted, or uncertain-outcome ProjectPipeline lane safely.
---

# Failure Recovery

1. Read instructions `11`, `17`, and `18`.
2. Classify failure and collect fingerprint, attempts, output digest, hypothesis, preserved work, and impact.
3. Apply canonical attempt limits; change strategy when same failure or unchanged output reaches policy limit.
4. For uncertain external writes, stop writes and reconcile remote state first.
5. For dirty Git, preserve and attribute work before cleanup.
6. For worker loss or split brain, fence stale authority before reassignment.
7. Persist a resume checkpoint; block only the affected lane unless the failure is global.
8. Produce an exact human intervention request only when automation cannot cross the boundary.
