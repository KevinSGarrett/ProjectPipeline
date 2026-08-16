# ADR-0026 — Keep Project Pipeline notification authority with Tauri-local and optional Apprise remote delivery

- **Status:** ACCEPTED
- **Authority:** engineering decision grounded in canonical requirements and bounded current upstream review
- **Source references:** `SRC-015:L000703-L000955`, `SRC-016:L000973-L001056`
- **Resolves:** `OPEN-DEC-0021`

## Context

The Operator Inbox requires local attention delivery, optional remote escalation, deduplication, quiet hours, acknowledgement, action links, and failure/retry handling. Delivery tooling must not become a second notification-policy or project-state authority.

Pass 21 re-qualified the existing candidate cohort. Tauri remains the bounded native desktop notification capability already selected for the Windows shell. Apprise provides a broad optional remote fan-out boundary without requiring Project Pipeline to own many provider-specific clients. ntfy remains a separately qualified self-hosted HTTP notification target/adapter and is not made a second broker.

## Decision

1. Project Pipeline remains the canonical Notification Broker. It alone classifies severity, applies deduplication, quiet-hours/escalation policy, records acknowledgement/resolution state, and chooses whether remote delivery is eligible.
2. Use the existing Tauri notification plugin boundary for local Windows notifications. Native notification click/action-link behavior remains unqualified until it is exercised in a real Windows/Rust/Tauri environment.
3. Use Apprise as the initial **optional** remote fan-out dependency behind `NotificationDeliveryService`.
4. Keep remote delivery disabled by default. Enabling it requires explicit configuration, credentials/secrets handling, version pinning, dependency qualification, and operational evidence.
5. Keep ntfy as an optional self-hosted HTTP target/adapter. It may be selected later without changing canonical broker semantics.
6. Delivery failures may schedule bounded retries, but a delivery adapter may never alter canonical incident, inbox, workflow, completion, authorization, or recovery state.

## Alternatives considered

- Windows notifications plus ntfy as the initial remote path
- Email or existing channels only
- Make Apprise or ntfy the canonical notification broker

## Consequences

- One deterministic policy/deduplication authority is preserved.
- Local notification capability remains available without requiring a remote service.
- Remote fan-out can expand without embedding many provider SDKs in the control plane.
- Apprise remains optional and was not installed/activated in the current execution environment.
- Native Windows notification click-through remains a documented qualification gap rather than an inferred success.

## Authority boundary

Project Pipeline retains canonical notification classification, incident/inbox state, authorization, policy, idempotency, audit, recovery, and completion authority. Tauri, Apprise, and ntfy provide delivery mechanics only.
