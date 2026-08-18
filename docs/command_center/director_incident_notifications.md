# Director Chat, Incident Manager, and Operator Notifications

## Purpose

Pass 21 turns the Command Center into an interactive operator surface while preserving the control-plane rule that UI/chat/notification state is never canonical project state.

## Director Chat

`DirectorChatService` supports `GLOBAL`, `PROJECT`, and `INCIDENT` scopes. Every response is grounded in a `CommandCenterSnapshot` fingerprint and, for incident scope, the canonical `IncidentCase`. The deterministic fallback responder is useful even when no qualified model adapter is configured.

Director Chat may return `DirectorActionProposal` records. A proposal always requires confirmation and never executes automatically. Any requested mutation must be reconstructed as a typed `CommandEnvelope` with `ActionIntent` and re-enter authentication, authorization, policy, idempotency, audit, and normal state-transition handling.

Private chain-of-thought/scratchpad data is excluded from the authorized Director context. The API exposes facts, evidence identifiers, response text, and typed proposals—not hidden reasoning.

## Incident Manager

`IncidentManager` wraps canonical `ExternalPreconditionIncident` records with an operator lifecycle:

`OPEN -> ACKNOWLEDGED -> RECOVERING -> VERIFIED -> RESOLVED`

Opening an incident creates/deduplicates an Operator Inbox item containing the exact human action, impact, blocked work, and post-action verification steps. `RESOLVED` is blocked until `verify_human_repair` proves that all supplied checks pass, stale assumptions were invalidated, and reconciliation completed.

## Notification Broker and delivery

`AttentionNotificationBroker` remains authoritative for priority, deduplication, severity, quiet-hours suppression, escalation, acknowledgement, and resolution. `NotificationDeliveryService` performs delivery mechanics only.

Initial policy from ADR-0026:

- local Windows notification boundary: Tauri notification plugin;
- remote fan-out adapter: optional Apprise dependency;
- optional self-hosted target/adapter: ntfy HTTP;
- remote delivery: disabled by default;
- bounded retries: three attempts with configured backoff;
- persisted delivery attempts: PPDB-0017.

Internal Command Center channels are recorded as delivered immediately. A Tauri desktop channel is returned as `CLIENT_ACTION_REQUIRED`, because the web/backend process cannot truthfully claim the native client displayed it. Remote adapter errors persist only a sanitized error category.

## Native desktop qualification boundary

The current environment does not provide Rust/Cargo or a Windows Tauri runtime. Source-level notification sending is present, but native action-link/click handling remains `UNQUALIFIED_NATIVE_CLICK_HANDLER`. The UI and evidence preview display that limitation explicitly.
