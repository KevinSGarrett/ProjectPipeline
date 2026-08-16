# Pass 23 Full End-to-End Integration upstream review

Reviewed for the Pass 23 end-to-end boundary on 2026-08-15 UTC.

## Cohort disposition

| Upstream | Pass 23 disposition | Runtime boundary |
|---|---|---|
| `UPSTREAM-011` Atlassian MCP | reuse bounded MCP adapter contract | no live Atlassian mutation without target credentials and explicit authority |
| `UPSTREAM-041` GitHub MCP | reuse bounded MCP adapter contract | local Git is real; remote PR behavior is mocked/dry-run unless live authority exists |
| `UPSTREAM-050` Hatchet | retain selected durable-backend adapter | SDK/service unavailable here; Project Pipeline local durable runtime supplies deterministic recovery coverage |
| `UPSTREAM-063` Playwright | reuse qualified local browser runtime | local Chromium verification remains executable |
| `UPSTREAM-086` Pydantic AI | retain optional provider adapter | package unavailable here; Agent Router mock providers exercise routing/failover without claiming Pydantic AI runtime qualification |
| `UPSTREAM-092` Schemathesis | retain local-only external CLI adapter | package/CLI unavailable here; contract behavior remains covered by Project Pipeline tests |
| `UPSTREAM-093` Toxiproxy | retain optional fault adapter | executable unavailable here; deterministic fault simulations remain authoritative evidence |
| `UPSTREAM-102` SWE-ReX | retain optional execution adapter/profile | upstream runtime unavailable here; no sandbox-runtime claim is made |
| `UPSTREAM-105` Testcontainers Python | keep selected/not activated | Python package and Docker runtime unavailable; no containerized integration claim is made |

## Authority and integration decision

Project Pipeline owns every journey transition and all canonical state. Upstreams may provide transport, runtime, testing, or sandbox implementations behind already-defined ports. A successful adapter contract is not evidence that the external executable, service, credentials, network path, or live target was exercised.

Pass 23 therefore uses real local repository/intake/control/scheduler/context/assurance/Command Center behavior, real local Git, and available local browser tooling; it uses deterministic Project Pipeline simulations or mocks for provider, Jira remote, GitHub remote, durable-backend, and incident failure cases; and it reports unavailable external legs as `EXPECTED_BLOCK`.

## Integration defect rule

E2E tests do not patch around product behavior. Defects discovered by a cross-subsystem journey are repaired in the owning subsystem. In this pass, review-separation and typed human-required behavior were already implemented but under-mapped; canonical-plan/policy recommendation conflict handling required an explicit control-authority disposition function and was repaired in `src/project_pipeline/control/authority.py`.

## Source-incorporation boundary

No upstream source is copied or substantially adapted in Pass 23. Existing adapters are reused and independently implemented E2E orchestration binds them together. Source-incorporation approval is therefore not required.
