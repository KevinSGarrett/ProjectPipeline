# Pass 21 Director Chat / Incident / Notification upstream review

Reviewed for the Pass 21 operator-interaction boundary on 2026-08-15 UTC.

## Cohort and disposition

| Upstream | Pass 21 disposition | Boundary |
|---|---|---|
| `UPSTREAM-003` AG-UI | retain bounded optional compatibility adapter | wire/event compatibility only; internal `EventEnvelope` remains canonical |
| `UPSTREAM-009` assistant-ui | mine interaction/accessibility patterns | no runtime dependency activation in this environment |
| `UPSTREAM-023` CopilotKit | mine HITL/shared-state presentation patterns | frontend-writable shared state is explicitly non-authoritative |
| `UPSTREAM-017` Apprise | optional remote-delivery dependency adapter implemented | remote fan-out only, disabled by default |
| `UPSTREAM-013` ntfy | optional self-hosted HTTP adapter implemented | delivery target only; not the canonical broker |
| `UPSTREAM-103` Tauri notification plugin | retain bounded local desktop source boundary | notification permission/send only; native action-click handling still requires Windows qualification |

## Current upstream evidence reviewed

- AG-UI repository and protocol documentation: event-based agent/user interoperability and MIT licensing.
- assistant-ui repository: React/TypeScript conversational UI primitives and interaction patterns.
- CopilotKit repository: human-in-the-loop, generative UI, and shared-state interaction patterns.
- Apprise repository: BSD-2-Clause multi-service notification library suitable for an optional fan-out adapter.
- ntfy repository/docs: HTTP publish/subscribe notification API with JSON requests and action/click metadata; licensing is deployment-sensitive (`Apache-2.0 OR GPL-2.0` as recorded in the catalog).
- Tauri official notification plugin documentation/workspace: capability-scoped desktop notification mechanics.

## Authority and security decision

No upstream owns Project Pipeline notification policy, deduplication, acknowledgement, incident state, authorization, idempotency, recovery, or audit. Remote delivery is disabled by default. Adapter failures are reduced to sanitized categories in canonical delivery evidence; secret-bearing exception messages are not persisted. Tauri shell capabilities are not expanded to shell/filesystem/network opener permissions for notification action links.

## Execution qualification

- Python adapter and deterministic browser evidence are executable in the current environment.
- The Apprise Python package is not installed as an active dependency; only the optional adapter boundary is implemented and tested through dependency injection.
- Rust/Cargo is unavailable, so native Windows Tauri notification click/action behavior is **not qualified** by this pass.
- No upstream source was copied into Project Pipeline.
