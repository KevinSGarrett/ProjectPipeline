# Command Center Backend and Realtime API

Pass 19 implements the operator-facing backend boundary without making UI state authoritative.

## Authority

`EventEnvelope`, the Control Kernel, persistence, policy, evidence, and the independent Completion Gate remain authoritative. The Command Center is a projection and typed-control client. It cannot declare completion, rewrite project state, or execute free-form chat text as a mutation.

## API

The FastAPI application factory exposes authenticated status, inbox, timeline, SSE, WebSocket, Director-context, capability, and typed-control endpoints. The default authenticator denies all protected access until an explicit token validator is supplied. `/healthz` is the only public endpoint.

Realtime reconnect uses `EventEnvelope.sequence` as a cursor. Retained events can be replayed before a live subscription resumes. UI caches are replaceable projections.

## Director and control

Director context contains grounded current projection facts and source identifiers and explicitly excludes private reasoning. Any mutation requires a `CommandEnvelope` containing a matching `ActionIntent`; the gateway then invokes the normal `CommandProcessor` after an injected authorization/policy decision.

## AG-UI boundary

Pass 19 activates AG-UI as a protocol compatibility boundary, not as canonical state. Internal `EventEnvelope` objects are translated into compatible lifecycle, text, state-snapshot, and custom-event documents at the edge. Project Pipeline does not copy upstream source code and does not expose chain-of-thought/private reasoning.

## Notifications

The Attention/Notification Broker ranks items from severity, critical-path impact, blocked work, duration, recoverability, and operator awareness. It deduplicates by stable keys and enforces quiet-hour routing. Notifications alone never change project state; operator actions return through typed control commands.

## Persistence and recovery

`PPDB-0016_command_center_realtime` adds event replay, inbox, notification-decision, and control-request audit tables for SQLite and PostgreSQL, with reversible down migrations. The realtime layer can be rebuilt from canonical state plus durable events.
