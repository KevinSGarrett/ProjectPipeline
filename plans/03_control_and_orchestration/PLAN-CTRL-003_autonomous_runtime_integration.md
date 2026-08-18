# PLAN-CTRL-003 — Autonomous Runtime Integration and Unattended Qualification

- **Status:** `ACTIVE`
- **Authority:** operator correction; `SRC-014:L000001-L000087`; `SRC-015:L000001-L000113`
- **Outcome requirement:** `REQ-PDEF-0011`
- **Owning epic:** `PP-EPIC-000036`

## PLAN-CTRL-003:SEC-01 Product outcome and terminal truth

ProjectPipeline is a continuously operating local-first autonomous engineering organization, not a library collection or an advisory chat responder. It accepts project inputs, compiles and validates a project model, selects genuinely missing work, executes compatible work through isolated lanes, verifies results, integrates accepted changes through governed repository operations, reconciles Jira, recomputes project state, and selects the next ready work until the independent Completion Gate reports `COMPLETE` for the integrated, released, and operationally qualified system.

Model repair, source coverage, class existence, mocked remotes, deterministic simulation, local component tests, generated evidence, Jira status, or an Autonomy Runtime skeleton cannot satisfy this outcome by themselves.

## PLAN-CTRL-003:SEC-02 Persistent runtime composition

Implement one persistent supervisor/service boundary that composes the Project Intake Compiler, verified project model, Project Control Kernel, Build Sequencer, Dynamic Lane Scheduler, resource leases and fencing, Context Broker and Compiler, Agent/Provider/Tool Router, durable orchestration, worker dispatch and result collection, Execution Assurance and Verification Director, Repository/GitHub Steward, Jira Steward, evidence and truth registries, Recovery Director, Budget Governor, Command Center projections, Director interaction, project-state recomputation, and automatic next-work continuation.

The supervisor must persist operation identity and state, be restart-safe and idempotent, reconcile unknown outcomes before retry, use bounded retries, and emit typed stop, blocked, and escalation states.

## PLAN-CTRL-003:SEC-03 Conflict-safe continuation and incidents

Admission is atomic over all claimed resources. Workspaces, leases, fencing tokens, worker health, result receipts, and integration order remain durable. A failed worker or unresolved operation is recovered or becomes a scoped `HUMAN_REQUIRED` incident. The incident preserves evidence, releases unnecessary resources, blocks dependent work, and immediately recomputes the graph so every unaffected lane continues. Only a genuinely global blocker may pause the project.

## PLAN-CTRL-003:SEC-04 Golden product journey

Qualification must run a small fixture project through actual input compilation, validated project modeling, missing-work detection, safe parallel selection, isolated real Git worktrees, qualified worker dispatch, immutable context receipts, a real implementation and tests, independent verification, governed PR and merge evaluation, Jira reconciliation, project-state recomputation, and automatic next selection. The journey must survive restart or worker loss, raise one deliberately unsolvable `HUMAN_REQUIRED` incident, continue an unaffected lane, expose truthful Command Center state, and retain evidence for every material transition.

Calling components sequentially in a test, using remote-only mocks, or generating an evidence record is insufficient.

## PLAN-CTRL-003:SEC-05 Live, Windows, and operator qualification

After the local-real and isolated-Git stages pass, qualify authorized GitHub/Jira sandbox or live behavior and at least one real worker/provider route. Then qualify the persistent supervisor and Command Center on Windows, including install, start, restart, recovery, operator incident interaction, truthful live projections, and rollback. Unavailable credentials or environments remain explicit blockers.

## PLAN-CTRL-003:SEC-06 Unattended and release qualification

Run the qualification ladder in order: deterministic unit/contract; local-real integrated journey; isolated real Git/worktree; authorized GitHub/Jira; real worker/provider; Windows service and Command Center; recovery/restart; unattended 24-hour; unattended 72-hour; released-state and post-release Completion Gate. Each stage binds exact source, code, configuration, environment, observations, failures, and recovery evidence. A later stage cannot inherit PASS from a mock or lower environment class.

## PLAN-CTRL-003:SEC-07 Cohesive vertical slices

Deliver this plan through six outcomes, not lifecycle-label PRs: source-to-control realignment; persistent supervisor composition; conflict-safe recovery and partial continuation; local-real Git/Jira golden journey; authorized live workers plus Command Center/Windows qualification; and unattended/release qualification. Focused checks run during development; expensive CI, independent review, manifest refresh, external reconciliation, and merge run once at each cohesive slice boundary.
