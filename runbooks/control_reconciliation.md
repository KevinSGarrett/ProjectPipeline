# Control Reconciliation Runbook

1. Run `project-pipeline control evaluate --root .` and retain the snapshot ID.
2. If graph construction fails, inspect the referenced dependency endpoint or cycle and correct the source-controlled Jira graph.
3. Run `project-pipeline control scope --root .` for source/work/implementation/evidence mismatches.
4. Run `project-pipeline control ready-plan --root .` before any state mutation.
5. Only after review, run the corresponding `ready-apply` command with explicit apply and approval flags.
6. Re-evaluate and confirm the graph fingerprint and readiness projection changed as expected.
7. Do not mark project completion from the control projection alone; final completion remains a separate verification authority.
