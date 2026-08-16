# Remote Jira adapter

The internal `JiraRemotePort` isolates Project Pipeline from provider-specific APIs. Its contract covers:

- capability and project-metadata discovery;
- paginated issue reads;
- individual issue reads;
- issue creation and field updates;
- workflow transitions;
- meaningful comments;
- issue links.

The Jira Cloud adapter uses an HTTPS site URL, user email, and an API-token secret reference. Secret values are resolved only when a live adapter is requested and are never emitted in configuration, logs, exceptions, snapshots, or artifacts.

Read operations may retry bounded transient, rate-limit, timeout, or unavailable responses. Mutating requests are not blindly retried. If the transport fails after dispatch or the provider returns an ambiguous server failure, the adapter reports `UNKNOWN_OUTCOME`; reconciliation must observe the remote issue before retry.

The deterministic mock uses the same port. It supports pagination, stable keys, idempotent replay, version conflicts, scheduled failures, and “persist then lose the response” simulation. Mock evidence is labeled mock/local verification, never live Jira verification.
