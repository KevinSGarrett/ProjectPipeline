# ADR-0028 — Authenticate Command Center with local OS identity and ephemeral loopback sessions

- **Status:** ACCEPTED
- **Authority:** engineering decision grounded in Command Center authentication, Windows-first operation, and recovery constraints
- **Source references:** `SRC-017:L000072-L000141`, `SRC-006:L001079-L001140`
- **Resolves:** `OPEN-DEC-0018`

## Context

The Command Center must be usable as a Windows desktop application and as an authenticated network-accessible interface. Authentication cannot wait for an external identity provider, and default exposure cannot be a LAN or Tailscale listener. Tokens written to HTML, argv, or a checkout-local token file create recoverable secret residue.

## Decision

1. Local OS identity plus an ephemeral in-memory session bearer is the Command Center authentication mechanism.
2. The live server binds loopback only (`127.0.0.1`, `localhost`, or `::1`) by default.
3. Bootstrap uses a one-time nonce exchanged over loopback. The nonce is not a session token, is not injected into HTML, and is deleted from any handshake file after first redeem.
4. Session tokens stay in process memory. They are not written to `localStorage`, `sessionStorage`, IndexedDB, installed config, or a persistent token file.
5. Non-loopback binds are rejected unless a later accepted profile explicitly enables them **and** requires authentication plus TLS. That profile is not admitted by this decision.
6. OIDC-capable local service and mutual TLS plus operator accounts remain rejected alternatives for the default Windows desktop and loopback service.

## Alternatives considered

- Local OS identity plus session auth
- OIDC-capable local service
- Mutual TLS plus operator accounts

## Consequences

- Desktop and browser clients must redeem a loopback handshake before calling authenticated APIs.
- Remote/LAN exposure remains a separate high-impact decision with TLS and identity controls.
- Recovery after process loss issues a new nonce and session; stale tokens are rejected.
- Existing deny-anonymous Command Center API behavior is preserved.
