# PLAN-GOV-003 — Repository and GitHub Stewardship

**Plan ID:** `PLAN-GOV-003`  
**Status:** Active  
**Authority:** Source-derived requirements with required implementation detail  
**Primary requirements:** `REQ-GOV-0004`, `REQ-GOV-0014`, `REQ-GOV-0015`, `REQ-GOV-0016`, `REQ-GOV-0017`, `REQ-GOV-0018`, `REQ-GOV-0019`, `REQ-GOV-0021`, `REQ-GOV-0023`, `REQ-GOV-0024`, `REQ-RES-0011`, `REQ-RES-0017`, `REQ-SCHED-0012`, `REQ-ASSURE-0026`

## PLAN-GOV-003:SEC-01 Repository Steward authority

The Repository Steward owns deterministic repository observations, branch and worktree policy, resource ownership, pull-request state, review/check evidence, cleanup proposals, and post-merge reconciliation. Workers do not receive implicit authority to mutate shared Git or GitHub state. Local inspection is read-only by default; local mutations require explicit apply intent; remote mutations require a separately approved action intent. Source: `SRC-007:L000649-L000669`, `SRC-007:L001098-L001128`, `GOV-001:L000518-L000532`.

## PLAN-GOV-003:SEC-02 Branch contract and work-in-progress preservation

Implementation work uses short-lived work-item-linked branches with an explicit base and intended merge target. The Branch Guardian rejects direct implementation on the default branch, detects detached HEAD state, records upstream divergence, and preserves dirty or unpublished work rather than deleting it. Cleanup is prohibited when meaningful work is unpreserved. Source: `SRC-007:L000670-L000798`, `SRC-006:L000479-L000518`.

## PLAN-GOV-003:SEC-03 Worktree isolation and resource ownership

Parallel repository modification uses isolated worktrees or equivalent sandboxes. Every active workspace can claim files, directories, schemas, databases, ports, environments, or repository-level resources. Overlapping active claims owned by different work items fail closed. Worktree creation and removal are explicit operations, and dirty registered worktrees cannot be removed by the steward. Source: `SRC-001:L000492-L000538`, `SRC-007:L000670-L000712`, `SRC-007:L001004-L001075`.

## PLAN-GOV-003:SEC-04 Pull-request, review, and check model

Pull-request state is modeled independently from any provider UI. A snapshot records immutable head/base identities, draft and mergeability state, latest review decisions, and check-run results. Review aggregation uses the latest observed decision per reviewer. Required checks are evaluated by stable name and head SHA so stale success from an earlier commit cannot satisfy the gate. Source: `SRC-007:L000799-L000925`, `SRC-008:L000986-L001015`.

## PLAN-GOV-003:SEC-05 Merge Gate

The Merge Gate is deterministic and fail closed. A pull request is merge-ready only when it is open, not draft, not known to conflict, still at the expected head SHA, satisfies required checks, meets required approval count, has no current changes-requested decision, and has no repository-governance blocker. Unknown mergeability is surfaced as a warning; unknown or changed head state prevents an authorized merge from silently applying to a different revision. Source: `SRC-007:L000886-L000925`, `SRC-008:L000986-L001015`.

## PLAN-GOV-003:SEC-06 GitHub provider boundary and mutation safety

GitHub REST operations are isolated behind a provider-neutral port. Read operations may use bounded retries for transient failures. Mutating requests are not blindly retried when transport outcome is uncertain. Every planned write has a semantic fingerprint, idempotency key, actor, correlation identity, optional expected head SHA, and authorization identity. A potentially committed write with a lost response becomes `UNKNOWN_OUTCOME` and requires reconciliation before retry. Source: `SRC-007:L001098-L001128`, `SRC-006:L000695-L000735`.

## PLAN-GOV-003:SEC-07 Cleanup and stale-branch reconciliation

Cleanup begins with classification rather than deletion. The default branch, branches attached to active worktrees, branches containing unmerged local work, and dirty workspaces are protected. Only branches that are demonstrably merged and detached from active workspaces can become cleanup candidates. Remote deletion is independently approval-gated and must never be inferred merely from local absence. Source: `SRC-007:L000713-L000798`, `SRC-007:L000926-L001075`.

## PLAN-GOV-003:SEC-08 Persistence and recovery

Repository ownership claims, merge-gate evaluations, planned operations, receipts, and unknown outcomes are persisted transactionally. Local state preserves operator intent through GitHub outages. Recovery queries the external provider, compares the observed branch or pull-request state with the persisted operation fingerprint and expected head, and marks the operation reconciled only when the effect is independently observed. Source: `SRC-006:L000695-L000735`, `SRC-007:L001004-L001128`.

## PLAN-GOV-003:SEC-09 Operator and CLI contract

The CLI exposes machine-readable local inspection, branches, worktrees, Branch Guardian, ownership, cleanup, remote snapshots, pull-request inspection, Merge Gate evaluation, and merge planning. Destructive or state-changing behavior is dry-run or deny-by-default. Local mutations require explicit apply plus approval. Live GitHub mutations additionally require an approved `github.steward` action intent and configured external-write policy. No local mock result is labeled live external verification. Source: `GOV-001:L001224-L001290`, `GOV-001:L001394-L001420`.

## PLAN-GOV-003:SEC-10 Verification and completion boundary

Verification includes domain, local-Git, ownership, adapter, mock-provider, persistence, CLI, fault, and repository-contract tests. The real HTTP adapter is contract-tested without credentials. Live GitHub verification remains separately blocked until a repository, integration identity, token reference, permissions, branch-protection rules, and bounded write authorization are supplied. Post-merge behavior must eventually be reverified against the integrated target state before project completion can rely on it. Source: `SRC-008:L000986-L001015`, `GOV-001:L001277-L001290`.
