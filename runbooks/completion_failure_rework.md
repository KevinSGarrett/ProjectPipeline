# Completion Failure Rework Runbook

Use the Completion Gate's typed failures as rework routes rather than repeatedly asking an agent to “try again.”

1. Capture the exact gate snapshot fingerprint and failed question numbers.
2. Route each failure through `completion.question.N` and retain the original evidence record.
3. If evidence is stale, rerun the relevant independent verification rather than editing the old evidence.
4. If evidence is unknown or blocked, preserve that truth state and identify the missing prerequisite.
5. If the same recovery action repeats without measurable progress, apply Loop Guard and require a materially novel recovery plan or escalation.
6. If remediation expands behavior or file scope, evaluate it against the frozen Scope Contract before implementation.
7. Rerun only affected verification plus required regression, append new evidence, and recompute the gate from a new snapshot.
8. Never edit a failed or stale evidence artifact to make it appear passing, and never mark `COMPLETE` manually.
