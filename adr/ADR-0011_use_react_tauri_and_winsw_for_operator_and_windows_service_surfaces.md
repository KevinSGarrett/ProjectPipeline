# ADR-0011 — Use React, Tauri, and WinSW for operator and Windows service surfaces

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-010:L001338-L001352`, `SRC-016:L001500-L001508`, `SRC-016:L002282-L002290`
- **Date:** `2026-08-14`

## Context

The Command Center must be network-accessible, accessible in a browser, capable of Windows desktop integration, and independent from backend daemon uptime.

## Decision

Build the operator interface as a React web application. Package the Windows desktop shell with Tauri and use only narrowly authorized official plugins. Run Windows-native long-lived backend entry points under WinSW; containerized or WSL services use their native supervisors. The internal realtime event model remains authoritative; an AG-UI compatibility adapter may expose the supported operator event subset. The desktop process is a client and must not own canonical state or critical daemon lifecycle.

## Alternatives considered

- Build a Windows-only native UI that cannot operate remotely.
- Keep critical services alive only while the desktop shell is open.
- Use an unrestricted desktop shell with broad filesystem and process access.
- Make an external UI protocol the authoritative project event model.

## Consequences

The web application can run without desktop packaging. Tauri permissions and plugin scopes require policy review. Service installation remains a later deliverable and is not implied complete by this selection.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
