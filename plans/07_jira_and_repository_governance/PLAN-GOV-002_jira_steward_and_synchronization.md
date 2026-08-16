# PLAN-GOV-002 — Jira Steward and Synchronization Architecture

- **Plan ID:** `PLAN-GOV-002`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus required implementation detail
- **Source basis:** `SRC-007:L000341-L000391`, `SRC-007:L000393-L000480`, `SRC-007:L000539-L000648`, `SRC-007:L001080-L001128`, `SRC-006:L000649-L000694`, `SRC-006:L002214-L002251`, `GOV-001:L000949-L001158`, `GOV-001:L001503-L001516`

## PLAN-GOV-002:SEC-01 Authority and ownership

The Jira Steward is the only Project Pipeline component authorized to convert an approved Jira action intent into a remote API mutation. The source-controlled `/jira` mirror owns stable local identity, detailed requirement and plan references, rich relationship semantics, and compact AI retrieval. Connected Jira remains the external collaborative work-management surface. Neither side is overwritten silently; differences become explicit reconciliation operations or conflicts.

## PLAN-GOV-002:SEC-02 Typed local work-item model

Every local issue is parsed into a strict immutable model. The model validates identifier/type agreement, parent rules, source references, plan line references, dependencies, blockers, relationship targets, acceptance-criterion identities, verification records, lifecycle state, and completion evidence. Serialization is deterministic, round-trippable, and fingerprinted. The local JSON records and generated indexes remain independently rebuildable.

## PLAN-GOV-002:SEC-03 Lifecycle and transition readiness

Project Pipeline normalizes remote workflows into `DISCOVERED`, `BACKLOG`, `READY`, `IN_PROGRESS`, `REVIEW`, `VALIDATION`, `MERGE_READY`, and `DONE`, with `BLOCKED`, `FAILED`, `CANCELLED`, and `DEFERRED` as side states. Remote names are configured explicitly. Transition readiness checks assignment, implementation evidence, branch state, required tests, acceptance criteria, independent review, blockers, and completion evidence before completion-oriented transitions.

## PLAN-GOV-002:SEC-04 Provider boundary

The remote port exposes capability discovery, project metadata, paginated issue retrieval, issue create/update, transitions, comments, and links. The Atlassian Jira Cloud adapter uses REST v3, reference-resolved credentials, typed errors, bounded read retries, pagination, read-after-write verification, and no blind retry of mutating requests. A deterministic mock implements the same port for contract, pagination, idempotency, rate-limit, outage, and unknown-outcome tests.

## PLAN-GOV-002:SEC-05 Snapshots and remote observations

A remote snapshot is immutable, complete or explicitly partial, ordered by remote key, timestamped, and content-fingerprinted. Snapshots retain only the remote fields needed for identity, hierarchy, status, reconciliation, comments, links, attachments, and verification. Stable local IDs are carried in a managed label or configured field. Remote observations never become local source authority merely because they were fetched.

## PLAN-GOV-002:SEC-06 Deterministic diff and reconciliation

Reconciliation compares the local semantic fingerprint and remote snapshot by stable local ID and remote key. It emits deterministic operations for issue creation, field updates, status transitions, mapping records, comments, links, or explicit local acceptance workflows. Duplicate mappings, remote-only issues, unmapped status, hierarchy disagreement, concurrent divergence, stale observations, and completion disagreement become typed conflicts with required resolution text.

## PLAN-GOV-002:SEC-07 Transactional outbox and unknown outcomes

Remote-write operations are persisted before execution with a stable operation ID, semantic request fingerprint, idempotency key, expected remote version, approval requirement, and state. A successful operation is recorded with its remote identity and post-write observation. A connection loss or server failure after dispatch is `UNKNOWN_OUTCOME`: automatic replay stops, the outbox retains the operation, and reconciliation must determine whether the remote effect occurred before any retry.

## PLAN-GOV-002:SEC-08 Comments and status hygiene

Comments preserve decisions, blockers, scope changes, review requests/findings, recovery handoffs, validation evidence, and completion summaries. Low-value activity narration is rejected. Remote status cannot assert completion ahead of evidence-backed local state. In collaborative authority mode, remote changes may be proposed for local acceptance, but remote `DONE` requires human review when the local record has not satisfied completion evidence.

## PLAN-GOV-002:SEC-09 Import, export, and dry-run

The local mirror exports as one deterministic typed bundle for transport and audit. An imported bundle is compared against source-controlled records and never applied automatically. Synchronization is dry-run by default. Remote application requires an approved `jira.steward` action intent, matching target and operation, an authorization identifier, enabled external-write policy, and available secret references. Mock execution is never labeled live verification.

## PLAN-GOV-002:SEC-10 Verification and operations

The Jira Steward is verified through unit, schema, repository, migration, adapter, pagination, reconciliation, outbox, idempotency, comment, CLI, fault, and clean-extraction tests. Operators can validate, export, compare imports, capture snapshots, create plans, inspect status, dry-run synchronization, and submit governed comments. Live Jira verification remains externally blocked until an authorized site, project, user, token, field mapping, workflow mapping, and remote-write approval are supplied.
