---
name: project-bootstrap
description: Cold-start or rehydrate a ProjectPipeline session from repository state without prior chat.
---

# Project Bootstrap

1. Read root `AGENTS.md` and instructions `00`, `01`, and `03`.
2. Run `python scripts/instruction_cold_start.py --root .`.
3. Run doctor, repository validation, Jira validation, control evaluate/sequence, and instruction validation.
4. Inspect Git state; classify exported snapshots explicitly.
5. Record a session checkpoint with current control, Jira, Git, external, worker, and evidence state.
6. Route the selected work through `INSTRUCTION_COVERAGE_MATRIX.json`.

Stop the affected action for secrets, hidden benchmark material, uncertain remote writes, unpreserved destructive scope, failed required gates, or unresolved authority conflict.
