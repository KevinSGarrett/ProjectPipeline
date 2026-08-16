# Pass 16 Verification Harness

The verification harness turns the Execution Assurance plan into executable, content-addressed evidence. It does not own completion state; the Completion Gate consumes its results.

## Operating model

- `verification plan` shows the deterministic check portfolio.
- `verification impact --changed-path ...` derives the required verification categories from controlled changes and requirement links.
- `verification tools` reports exact upstream/runtime activation truth.
- `verification run` executes the local Pass-16 portfolio and writes evidence.
- `verification journeys` runs golden journeys without external writes.
- `verification browser` generates and verifies the local HTML evidence report with Playwright when Chromium is available.
- `verification simulate` executes deterministic golden/property/fault scenarios.
- `verification status` reads persisted local verification state.

Required checks are never silently skipped. Missing required capability is `BLOCKED`, not `PASS`. Unclassified changed paths fail safe to contract/post-merge verification instead of producing an empty test-impact set.

## Browser evidence

The current Pass-16 browser target is the deterministic verification report, not the future Command Center. It is intentionally dependency-free HTML rendered from governed repository state. Desktop and mobile screenshots, overflow, console errors, semantic accessibility checks, and load timing are recorded.

## External verification tools

Optional adapters exist for mutmut, axe-core bundle use, Lighthouse CI, Playwright MCP, Schemathesis, Toxiproxy, Promptfoo/Inspect AI, and agent-browser. Absence of an executable is represented truthfully. Project Pipeline never auto-installs a latest tool or downloads browser/security code at verification time.

## Evidence authority

Verification output becomes evidence only after hashing and provenance capture. An upstream tool cannot mark Jira work Done or certify completion. Final completion remains the deterministic fifteen-question Completion Gate.


## Golden-journey contract

Every golden journey declares its environment, setup steps, action sequence, expected observable results, cleanup steps, preserved-evidence expectations, requirement links, risk, and objective observations. A journey is not considered a valid end-to-end acceptance definition when any of those required dimensions is absent.

## Fault portfolio

The deterministic fault portfolio covers provider errors, provider latency/timeouts, network loss, lost backend acknowledgement, worker termination, provider quota exhaustion, and unavailable/unqualified optional dependencies. The harness records observed behavior for each scenario and requires every configured fault scenario to pass; a missing external fault-injection binary is never translated into a fabricated live execution claim.
