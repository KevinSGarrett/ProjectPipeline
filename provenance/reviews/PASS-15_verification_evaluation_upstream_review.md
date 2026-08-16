# Verification and Evaluation Upstream Review — Execution Assurance Gate

This review satisfies the permanent upstream-first gate for the Execution Assurance / Completion Gate subsystem. Selection never grants completion authority: Project Pipeline remains the deterministic final authority.

## Candidate set and decisions

- `UPSTREAM-015` boxed/mutmut — keep as a later risk-selected Python mutation-testing dependency for the verification harness; no activation in the Completion Gate core.
- `UPSTREAM-027` dequelabs/axe-core — keep as the browser/accessibility engine for later visual/accessibility verification; no activation in the Completion Gate core.
- `UPSTREAM-032` EleutherAI/lm-evaluation-harness — mine model-evaluation test patterns; it cannot certify project completion.
- `UPSTREAM-044` GoogleChrome/lighthouse-ci — keep for later web performance/quality verification; no activation in the Completion Gate core.
- `UPSTREAM-051` HypothesisWorks/hypothesis — focused review complete; MPL-2.0 resolved. Qualify for deterministic property/state-machine tests of control, reconciliation, and assurance invariants.
- `UPSTREAM-063` microsoft/playwright — retain selected Apache-2.0 browser runtime for later golden-journey/browser verification. Completion Gate consumes resulting evidence only.
- `UPSTREAM-064` microsoft/playwright-mcp — focused review complete; qualify as an optional agent-mediated browser inspection component while Playwright remains the browser execution/evidence substrate.
- `UPSTREAM-085` promptfoo/promptfoo — reuse the existing read-only evaluation CLI adapter for AI/model/red-team evidence; no self-certification.
- `UPSTREAM-092` schemathesis/schemathesis — focused review complete; qualify for OpenAPI/property-based API verification in the later verification harness.
- `UPSTREAM-093` Shopify/toxiproxy — focused review complete; qualify for controlled network fault-injection evidence in later resilience verification.
- `UPSTREAM-101` stryker-mutator/stryker-js — mine mutation-testing patterns for front-end/TypeScript verification; no baseline dependency.
- `UPSTREAM-108` UKGovernmentBEIS/inspect_ai — MIT license resolved; reuse the existing evaluation CLI adapter for independent model/tool evaluations.
- `UPSTREAM-111` vercel-labs/agent-browser — focused review complete; qualify as an optional agent-browser convenience boundary, never as the source of final browser truth.

## Source-level evidence used

- Hypothesis `16f24b76015dbaabca40608eb9e73b46ac64e249`: core settings/stateful APIs; `LICENSE.txt` resolves the repository to MPL-2.0.
- Playwright `d5a185a894ab3ab17ff77a44e116a1339c6bdaed`: browser/test runtime and trace/screenshot/retry surfaces.
- Playwright MCP `7e0457a7cbf88823bf0146d12c46ae12c6818247`: structured browser snapshot and tool interface.
- Promptfoo `fded938b65a81e12070a66e90ca4ad2d42a8062e`: evaluation CLI/output/assertion surfaces; existing Project Pipeline adapter reused.
- Schemathesis `c60bde9733dad2fc4ef8f6451f58a10e8c7b6663`: API/property/stateful verification architecture.
- Toxiproxy `94d6d4b3c385e48534622b138da61e95014196d5`: deterministic network fault injection.
- Inspect AI `c07dff4f8c029d92e785bf4109f5ed43f582c880`: evaluation/log/scoring surfaces; `LICENSE` resolves to MIT; existing adapter reused.
- agent-browser `548b159b30eef119ccf6846c8bc807d0eaa3f6f8`: browser snapshot/ref/command model.

## Authority boundary

The upstream tools are evidence producers or test harnesses. They cannot transition Jira work to Done, convert an unknown result to passing, waive stale evidence, satisfy independent-review requirements, or certify Project Pipeline completion. The deterministic Completion Gate is evaluated from canonical requirements, Jira, traceability, repository state, fresh evidence, review independence, and explicit external blockers.

No upstream source is copied by this review. Any source adaptation still requires the bounded source-incorporation gate.
