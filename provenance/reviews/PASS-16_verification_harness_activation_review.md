# Pass 16 Verification Harness Upstream Activation Review

This activation review consumes the completed Pass 15 verification/evaluation review and does **not** repeat the historical three-round corrective program. It satisfies the permanent upstream-first continuation rule before material Pass 16 harness implementation.

## Environment preflight

- Python Playwright package: observed `1.57.0`.
- System Chromium: observed at `/usr/bin/chromium`; headless launch verified against the local filesystem with no network dependency.
- Hypothesis Python package: not installed in this execution environment.
- Schemathesis CLI/package: not installed.
- mutmut CLI: not installed.
- Toxiproxy server/CLI: not installed.
- Lighthouse CI (`lhci`): not installed.
- Playwright MCP binary: not installed.
- agent-browser binary: not installed.
- Promptfoo/Inspect AI: existing Project Pipeline CLI adapters retained; no live external executable qualification is claimed.

Absence of an optional executable does not become a passing claim. Pass 16 uses Project Pipeline-owned deterministic verification for the category when possible and records the upstream runtime as not live executed.

## Candidate decisions

- `UPSTREAM-015` boxed/mutmut — external CLI adapter implemented. The binary is not installed; Pass 16 executes isolated repository mutation probes instead and does not claim mutmut execution.
- `UPSTREAM-027` dequelabs/axe-core — repository-local reviewed-bundle profile implemented. The axe bundle is not installed; Pass 16 executes a Playwright DOM semantic accessibility baseline and does not claim axe execution.
- `UPSTREAM-032` EleutherAI/lm-evaluation-harness — test-pattern source only; no runtime activation.
- `UPSTREAM-044` GoogleChrome/lighthouse-ci — local-target CLI adapter implemented. `lhci` is not installed; representative local performance budgets are executed internally and no Lighthouse score is claimed.
- `UPSTREAM-051` HypothesisWorks/hypothesis — MPL-2.0 qualification retained. The dependency is not installed; deterministic generated property probes execute now while the Hypothesis dependency remains selected-not-activated.
- `UPSTREAM-063` microsoft/playwright — activated as the browser execution/evidence substrate. Python package `1.57.0` and system Chromium are executed directly. Project Pipeline owns result interpretation.
- `UPSTREAM-064` microsoft/playwright-mcp — optional headless process profile implemented; binary not installed. Direct Playwright remains authoritative browser evidence.
- `UPSTREAM-085` promptfoo/promptfoo — existing external CLI evaluation adapter reused; external binary not live-qualified in this pass.
- `UPSTREAM-092` schemathesis/schemathesis — local-only OpenAPI CLI adapter implemented; binary not installed. Existing protocol-contract tests provide current API evidence.
- `UPSTREAM-093` Shopify/toxiproxy — optional local fault-runtime profile implemented; server not installed. Deterministic in-process worker/network-equivalent failure simulations provide current fault evidence.
- `UPSTREAM-101` stryker-mutator/stryker-js — mutation-testing pattern source only; no runtime activation.
- `UPSTREAM-108` UKGovernmentBEIS/inspect_ai — existing external evaluation adapter reused; external runtime not live-qualified.
- `UPSTREAM-111` vercel-labs/agent-browser — optional CLI profile implemented; binary not installed. It cannot supersede direct browser evidence.

## Authority boundary

Every upstream remains an evidence producer, runtime, adapter, or test-pattern source. None can mark Jira work Done, waive stale or blocked evidence, convert unknown results into passing facts, or certify project completion. The deterministic Project Pipeline Completion Gate remains the only completion authority.

## Pass 16 implementation rule

Required verification categories may be `PASS`, `FAIL`, or explicitly `BLOCKED`; required checks may never be silently `SKIPPED`. Optional upstream absence is represented truthfully and does not erase internally executable verification for the same assurance category.
