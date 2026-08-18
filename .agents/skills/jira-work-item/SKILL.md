---
name: jira-work-item
description: Execute one ready ProjectPipeline Jira work item with bounded context, traceability, and reconciliation.
---

# Jira Work Item

1. Read instructions `05`, `06`, and `12`.
2. Confirm the item is ready through Project Control, not board position.
3. Load the issue, parent, graph edges, `jira/source_context/<ID>.md`, referenced requirements, plan sections, ADRs/policies, code, tests, and evidence.
4. Search for completed or overlapping work before claiming resources.
5. Create the work/resource claim and isolated branch/worktree.
6. Implement one cohesive acceptance boundary and run risk-proportional tests/evidence.
7. Update Jira autonomously at meaningful lifecycle points through Jira Steward; transition remote `Done` when local `DONE`, evidence, integrated-main verification, provisioned credentials, and readback preconditions pass.
8. Reconcile remote state before retrying any uncertain write.
9. Mark complete only after integration, post-merge verification, evidence, and local/remote reconciliation. Never park eligible Jira work for human approval.
