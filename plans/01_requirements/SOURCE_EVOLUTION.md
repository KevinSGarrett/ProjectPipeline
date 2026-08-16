# Source Evolution Register

Records: `15`

## SOURCE-EVOLUTION-0001 — Exact Duplicate

**Sources:** `SRC-017`, `SRC-018`

**Handling:** Count as one evidentiary statement; retain both source records for provenance.

**Requirement effect:** Requirements cite SRC-017 unless a historical reference specifically requires SRC-018.

**Linked requirements:** `REQ-REQ-0002`, `REQ-REQ-0007`

Earlier ranges: `SRC-017:L000001-L001336`

Later ranges: `SRC-018:L000001-L001336`

## SOURCE-EVOLUTION-0002 — Prefix Overlap

**Sources:** `SRC-005`, `SRC-006`

**Handling:** Do not treat shared prefix material as independent confirmation; prefer SRC-006 for combined resilience and Command Center context.

**Requirement effect:** Duplicate-aware evidence keys collapse overlapping ranges.

**Linked requirements:** `REQ-REQ-0002`, `REQ-REQ-0007`

Earlier ranges: `SRC-005:L000001-L001065`

Later ranges: `SRC-006:L000001-L001065`

## SOURCE-EVOLUTION-0003 — Governing Prompt Aliases

**Sources:** `Initial_Prompt.txt`, `Pasted markdown`

**Handling:** Treat as substantively equivalent aliases after normalization; use GOV-001 as the canonical line-addressable execution contract.

**Requirement effect:** Raw hashes remain preserved while requirements cite GOV-001.

**Linked requirements:** `REQ-PDEF-0001`, `REQ-REQ-0002`

## SOURCE-EVOLUTION-0004 — Research Refinement

**Sources:** `SRC-010`, `SRC-011`, `SRC-016`

**Handling:** Later research narrows and updates candidate roles; no candidate is adopted solely from any research pass.

**Requirement effect:** Upstream decisions remain EVALUATE_LATER until focused inspection.

**Linked requirements:** `REQ-UPSTREAM-0011`, `REQ-UPSTREAM-0003`

Earlier ranges: `SRC-010:L000009-L001711`

Later ranges: `SRC-011:L000001-L001675`, `SRC-016:L000001-L002538`

## SOURCE-EVOLUTION-0005 — Role Narrowing

**Sources:** `SRC-001`, `SRC-002`

**Handling:** Gemini/Antigravity-style browser capability is treated as a bounded visual or exploratory worker, not control authority.

**Requirement effect:** Browser output remains untrusted and Playwright-style deterministic verification remains required.

**Linked requirements:** `REQ-AGENT-0011`, `REQ-CTX-0018`, `REQ-ASSURE-0025`

Earlier ranges: `SRC-001:L000734-L000755`

Later ranges: `SRC-002:L001290-L001314`

## SOURCE-EVOLUTION-0006 — Official Integration Preference

**Sources:** `SRC-010`, `SRC-011`, `SRC-016`

**Handling:** Official GitHub and Atlassian integrations receive evaluation priority over community wrappers.

**Requirement effect:** Adapter boundaries remain provider-neutral and no integration is yet adopted.

**Linked requirements:** `REQ-UPSTREAM-0012`, `REQ-GOV-0024`

Earlier ranges: `SRC-010:L000574-L000635`

Later ranges: `SRC-011:L000343-L000416`, `SRC-016:L000710-L000802`

## SOURCE-EVOLUTION-0007 — Orchestration Candidate Refinement

**Sources:** `SRC-003`, `SRC-010`, `SRC-011`, `SRC-016`

**Handling:** Preserve Temporal and DBOS as durability references and qualified alternatives; the latest source promotes Hatchet for initial direct use behind an internal port.

**Requirement effect:** ADR-0008 selects Hatchet initially while retaining Temporal and DBOS conformance candidates without allowing any backend to own project truth.

**Linked requirements:** `REQ-CTRL-0010`, `REQ-ARCH-0008`, `REQ-ARCH-0014`, `REQ-UPSTREAM-0011`

Earlier ranges: `SRC-003:L000882-L000961`, `SRC-011:L000102-L000184`

Later ranges: `SRC-016:L001752-L001756`, `SRC-016:L002223-L002230`

## SOURCE-EVOLUTION-0008 — Scheduler Concretization

**Sources:** `SRC-014`, `SRC-016`

**Handling:** The dynamic-lane concept is refined into a graph model with NetworkX and optional OR-Tools optimization.

**Requirement effect:** Graph semantics are required; optimizer dependency remains an open decision.

**Linked requirements:** `REQ-SCHED-0009`, `REQ-SCHED-0010`

Earlier ranges: `SRC-014:L000378-L000748`

Later ranges: `SRC-016:L000037-L000220`, `SRC-016:L001952-L002196`

## SOURCE-EVOLUTION-0009 — Ui Stack Refinement

**Sources:** `SRC-006`, `SRC-016`

**Handling:** The detailed Command Center requirements remain authoritative while later research supplies candidate protocols and libraries.

**Requirement effect:** UI technology remains open; functional and accessibility requirements are fixed.

**Linked requirements:** `REQ-UX-0001`, `REQ-ARCH-0014`

Earlier ranges: `SRC-006:L001079-L003060`

Later ranges: `SRC-016:L000803-L000972`

## SOURCE-EVOLUTION-0010 — Secrets Backend Staging

**Sources:** `SRC-009`, `SRC-016`

**Handling:** SOPS/age is the local-first candidate; OpenBao is a later multi-user candidate rather than an initial mandatory service.

**Requirement effect:** Secrets abstraction is required; backend selection remains open.

**Linked requirements:** `REQ-SEC-0017`, `REQ-ARCH-0006`

Earlier ranges: `SRC-009:L000008-L000009`

Later ranges: `SRC-016:L001057-L001176`

## SOURCE-EVOLUTION-0011 — Browser Authority Refinement

**Sources:** `SRC-002`, `SRC-011`

**Handling:** Playwright is the reproducible authority; browser-use agents are exploratory unless independently verified.

**Requirement effect:** Golden browser journeys require deterministic automation evidence.

**Linked requirements:** `REQ-ASSURE-0025`, `REQ-CTX-0018`

Earlier ranges: `SRC-002:L000516-L000884`

Later ranges: `SRC-011:L000850-L000884`

## SOURCE-EVOLUTION-0012 — Vector Default Narrowing

**Sources:** `SRC-010`, `SRC-011`

**Handling:** A vector database is no longer assumed as a default; structural and lexical retrieval must be benchmarked first.

**Requirement effect:** Vector backend remains an open decision and optional dependency.

**Linked requirements:** `REQ-CTX-0009`, `REQ-ARCH-0011`

Earlier ranges: `SRC-010:L000299-L000389`, `SRC-010:L000501-L000539`

Later ranges: `SRC-011:L000601-L000653`

## SOURCE-EVOLUTION-0013 — Local Model Boundary

**Sources:** `SRC-003`, `SRC-013`

**Handling:** Local model project-management assistance is retained, but deterministic Project Control Kernel authority is explicit.

**Requirement effect:** Local models may advise and triage but may not commit canonical transitions.

**Linked requirements:** `REQ-AGENT-0012`, `REQ-CTRL-0001`

Earlier ranges: `SRC-003:L000451-L000609`

Later ranges: `SRC-013:L000420-L000474`

## SOURCE-EVOLUTION-0014 — Platform Gap Expansion

**Sources:** `SRC-009`, `SRC-017`

**Handling:** The later gap audit adds identity, root of trust, transaction safety, lifecycle, retention, portfolio, and adoption controls to the earlier service list.

**Requirement effect:** These controls are modeled as first-class requirements rather than optional polish.

**Linked requirements:** `REQ-LIFE-0010`, `REQ-SEC-0008`, `REQ-ARCH-0005`

Earlier ranges: `SRC-009:L000003-L000030`

Later ranges: `SRC-017:L000009-L001217`

## SOURCE-EVOLUTION-0015 — Aws Phase Refinement

**Sources:** `SRC-001`, `SRC-012`

**Handling:** AWS remains optional but later source defines specific witness, ingress, DR, burst, credential, and phased-adoption responsibilities.

**Requirement effect:** Local-primary hybrid is required as the initial posture; exact services remain open.

**Linked requirements:** `REQ-INFRA-0012`, `REQ-RES-0015`

Earlier ranges: `SRC-001:L000867-L000940`

Later ranges: `SRC-012:L000001-L001056`
