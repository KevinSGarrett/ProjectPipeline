# Command Center Realtime Recovery Runbook

1. Treat the UI as disposable projection state; never promote a client cache to canonical state.
2. Confirm Control Kernel/persistence health before restoring operator mutation endpoints.
3. Reconnect from the last acknowledged `EventEnvelope.sequence`; replay retained events before live subscription.
4. If the cursor predates retention, fetch a fresh canonical snapshot and restart the cursor from the current sequence.
5. If notification delivery fails, preserve the Operator Inbox record and retry only channel delivery; do not duplicate the underlying incident/action.
6. If authentication or policy evaluation is unavailable, fail protected endpoints closed. Read-only health may remain available according to deployment policy.
7. After recovery, verify event ordering, inbox deduplication, typed-command authorization, and a current snapshot fingerprint before declaring the Command Center surface restored.
