# Operator notification delivery failure recovery

1. Confirm the canonical Operator Inbox item still exists and has not been resolved.
2. Inspect the broker decision: severity, quiet-hours result, escalation flag, and chosen channels.
3. Inspect the most recent `NotificationDeliveryAttempt`; do not infer delivery from the broker decision alone.
4. For `CLIENT_ACTION_REQUIRED`, verify the Tauri client is running and notification permission is granted. Do not mark native click-through qualified without Windows evidence.
5. For `RETRY_SCHEDULED`, allow the bounded retry schedule to proceed unless the incident has been resolved or policy changed.
6. For `FAILED`, inspect the sanitized error category and adapter health. Retrieve secrets only from the approved secret boundary; never paste tokens into incident/chat records.
7. If remote delivery is disabled by policy, do not bypass policy. Use the local Operator Inbox/desktop path or obtain the configuration/approval required to enable remote delivery.
8. After restoring delivery, send one controlled test notification, confirm duplicate suppression, acknowledge it, and attach evidence.
9. Reconcile the Operator Inbox and incident state before resuming affected work. Delivery success does not by itself resolve an incident.
