# PLAN-UPSTREAM-006 — Upstream Implementation Convergence

- **Plan ID:** `PLAN-UPSTREAM-006`
- **Status:** `ACTIVE`
- **Authority:** governing upstream-research contract, accepted Upstream Adoption Gate, terminal catalog dispositions, and verified implementation evidence
- **Source basis:** `GOV-001:L000797-L000876`, `GOV-001:L001219-L001285`, `GOV-001:L001364-L001385`, `SRC-016:L001691-L001832`, `SRC-016:L002181-L002303`

## PLAN-UPSTREAM-006:SEC-01 P0 convergence contract

The highest-priority upstream adoption queue is closed through executable integration rather than review status alone. Every P0 repository must end with an implemented adapter/dependency, an explicit evidence-backed defer/reject decision, or a genuine external blocker. `provenance/p0_convergence.json` is the machine authority for that closure and must exactly cover the P0 queue.

## PLAN-UPSTREAM-006:SEC-02 Worker execution infrastructure

SWE-ReX is integrated behind an optional Project Pipeline runtime adapter. The adapter uses the upstream deployment/runtime separation, executes argv without a shell, wraps deployment lifecycle, and requires Project Pipeline action-intent approval before mutating execution. External installation and live backend qualification remain separate from implementation truth.

## PLAN-UPSTREAM-006:SEC-03 Codex and Gemini worker adapters

Codex and Gemini CLI are integrated as optional headless workers behind Project Pipeline policy. Codex uses JSONL, ephemeral execution, read-only sandboxing for observation, and approval-aware workspace mutation; dangerous bypass options are forbidden. Gemini uses stream-JSON with `plan` for read-only work and `auto_edit` only after Project Pipeline approval; yolo mode is forbidden. Network/provider execution remains explicitly gated.

## PLAN-UPSTREAM-006:SEC-04 Repository context packaging

Repomix is integrated as an optional context-packaging CLI. Project Pipeline retains its own Context Compiler authority while using Repomix for bounded repository packing/compression where useful. Security checking remains enabled, line references remain enabled, and token budgets are explicit. Remote configuration trust overrides and security-check bypass are prohibited.

## PLAN-UPSTREAM-006:SEC-05 Official GitHub and Atlassian MCP boundaries

The official GitHub and Atlassian MCP servers are represented by concrete secure profiles owned by Repository Steward and Jira Steward respectively. Profiles contain only endpoint/auth-reference/policy metadata, are read-only by default, and never embed secret values. Remote write capability requires the owning steward's approved ActionIntent; selection or profile existence is not a remote-write authorization.

## PLAN-UPSTREAM-006:SEC-06 Independent model evaluation

Promptfoo and Inspect AI are integrated behind evaluation adapters. Promptfoo uses explicit configuration/output paths, disables sharing, and applies bounded concurrency. Inspect AI uses a bounded eval/log interface. Networked provider evaluation is denied unless explicitly allowed. Neither evaluation framework is authoritative over project state; results become verification evidence for later Completion Gate decisions.

## PLAN-UPSTREAM-006:SEC-07 Security and supply-chain verification tools

Gitleaks, OSV-Scanner, Cosign, and Zizmor are integrated as read-only verification adapters. Gitleaks uses current `git` scanning with full redaction; OSV-Scanner uses source scanning with machine JSON and never invokes risky automated remediation; Cosign performs verification only and requires immutable digest references; Zizmor defaults offline, strict collection, and versioned JSON. Tool installation and live CI qualification remain later operational activation work.

## PLAN-UPSTREAM-006:SEC-08 Activation and truth boundaries

`OPTIONAL_ADAPTER_IMPLEMENTED` and `EXTERNAL_CLI_ADAPTER_IMPLEMENTED` mean Project Pipeline contains a real tested integration boundary. They do not claim the upstream executable/package is installed, credentials exist, network/spend is authorized, or live external behavior was verified. Activation requires version qualification, license/provenance confirmation, least privilege, applicable secrets, policy authorization, and environment-specific contract tests.

## PLAN-UPSTREAM-006:SEC-09 Pass-12 upstream prerequisite

The context/delegation implementation may advance only when the P0 convergence ledger is `PASS`, every P0 record maps to an implemented usage or explicit closed outcome, all referenced integration/test paths exist, and repository validation confirms the permanent Upstream Adoption Gate. This prerequisite is independent from other external blockers and may not be bypassed through continuation prose.

## PLAN-UPSTREAM-006:SEC-10 Verification and future subsystem discipline

Dedicated integration tests cover safe command construction, network/write gating, lifecycle handling, path confinement, read-only defaults, machine-readable outputs, and prohibited unsafe modes. The complete repository regression and self-validator must remain green. Future subsystem work must continue consulting `provenance/upstream_adoption_gate.json`; P1/P2 candidates are qualified at their owning subsystem boundary rather than forgotten or falsely presented as current integrations.
