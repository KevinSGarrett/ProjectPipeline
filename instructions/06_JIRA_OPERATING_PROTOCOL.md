# Jira Operating Protocol

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-06` |
| Status | `ACTIVE` |
| Pack version | `1.2.0` |
| Primary domains | `jira` |
| Governing entry point | `AGENTS.md` |

## Authority split

The source-controlled `/jira` mirror is the rich local engineering representation and default authority mode is `SOURCE_CONTROLLED_LOCAL`. The remote `PP` project is a collaboration surface. Neither side is silently overwritten. Jira Steward snapshots, compares, plans, applies authorized changes, records outbox state, and reconciles uncertain outcomes.

Remote UI status is not the sole source of truth and is never completion proof.

The live `PP` collaboration workflow exposes only `To Do`, `In Progress`, and
`Done`. The preferred-status policy therefore projects discovered, backlog,
ready, deferred, and cancelled local work to `To Do`; active, review,
validation, merge-ready, blocked, and failed local work to `In Progress`; and
only locally `DONE` work to `Done`. Rich lifecycle truth remains in the local
mirror and structured remote description. Remote `Done` is autonomously
authorized only from evidence-backed local `DONE`; no human approval is
required. A remote-first `Done` observation never overrides incomplete local
truth and instead creates a deterministic evidence-reconciliation conflict.

## Before starting an item

Verify:

- local ID, issue type, parent/epic, and current state;
- dependency and blocker relationships;
- acceptance criteria and verification methods;
- source references and requirement IDs;
- plan IDs, section IDs, and line ranges;
- evidence requirements and freshness;
- current implementation and overlapping work;
- readiness and resource ownership.

Use `jira/source_context/<ID>.md` rather than loading all 368 records.

## Core commands

```bash
PYTHONPATH=src python -m project_pipeline jira validate --root .
PYTHONPATH=src python -m project_pipeline jira export --root . --output .local/exports/jira_mirror.json
PYTHONPATH=src python -m project_pipeline jira snapshot --root . --provider atlassian --output .local/jira/remote_snapshot.json
PYTHONPATH=src python -m project_pipeline jira plan --root . --provider mock --output .local/jira/plan.json
PYTHONPATH=src python -m project_pipeline jira sync --root . --provider mock
```

Live adapters require provisioned credentials through approved references, an authorization identity, `--apply`, `--approve`, and any required security mode. `--approve` records policy approval by the autonomous control plane; it is not a request for human approval. Start with a read-only snapshot or dry-run plan.

## Reconciliation

When local and remote differ:

1. preserve a timestamped remote snapshot;
2. classify each difference as expected projection, remote collaboration edit, stale state, conflict, or unknown write outcome;
3. apply the sync policy in `config/jira/sync_policy.json`;
4. create a deterministic plan with intended transitions and idempotency identities;
5. for `Done`, require evidence-backed local `DONE`, applicable scope-gate success, integrated-main verification, and deterministic issue identity;
6. apply autonomously authorized operations with idempotency and version guards;
7. read remote state again and record reconciliation evidence.

Do not import remote-only issues when policy disables it. Do not delete local detail to match a thinner remote representation.

## Meaningful updates

Update at lifecycle points such as work started, material blocker, decision, scope change, review requested, validated finding, PR opened, validation evidence, merged, or completion summary. Do not post every terminal command.

Use the governed comment kinds exposed by Jira Steward. Comments must not contain secrets, raw unredacted PII, or unsupported completion claims.

## New work items

Search first. A discovered gap becomes a new issue only when it has a real scope gap, authority classification, parent, acceptance, verification, dependencies, risk, and source/plan traceability. Do not create hundreds of micro-items to mirror every code edit.

## Completion

Do not transition an item to `DONE` because code exists, a test passed, a PR opened, or a model approves. The applicable Definition of Done and scope Completion Gate must be satisfied, integrated, evidenced, and reconciled. When those conditions hold and credentials are provisioned, the local and remote transitions are routine autonomously authorized writes and must not be parked for human review.

## Unknown outcome

If a Jira write may have succeeded before a timeout, stop write retries. Snapshot remote state, locate the idempotency identity or intended effect, reconcile, and retry only when the effect is absent and authority still exists.

## Test and benchmark Jira

PPQS Jira projects and issues are clearly namespaced, associated with a benchmark/run identity, and isolated from the real `PP` project. Record creation date, owner, lifecycle, reuse, evidence retention, and cleanup eligibility.
