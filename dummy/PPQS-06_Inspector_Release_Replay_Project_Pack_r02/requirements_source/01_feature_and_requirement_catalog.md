# Inspector Release Replay — Source Requirement Statements

The statements below are authoritative visible source material. ProjectPipeline must normalize and trace them into its own requirement and work registries.

## SRC-MI-FEATURE-01 — Packaged sandbox assets

Published packages include the web sandbox proxy and verify that installed-package application
widgets can load.

Primary actor: **package consumer**. Successful outcome: **the packaged artifact renders the sandboxed application flow**. Principal deliverable: **packaging rule and installed-package smoke**.

### SRC-MI-STATEMENT-0001 — Packaged sandbox assets: Core behavior

The Historical Release Replay implementation SHALL provide published packages include the web sandbox proxy and verify that installed-package application widgets can load.

Acceptance intent: Demonstrate that the packaged artifact renders the sandboxed application flow; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0013 — Packaged sandbox assets: Input and state validation

The Packaged sandbox assets capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, repo-only success cannot hide missing package files.

### SRC-MI-STATEMENT-0025 — Packaged sandbox assets: Interface contract

The public interfaces for Packaged sandbox assets SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for packaging rule and installed-package smoke.

### SRC-MI-STATEMENT-0037 — Packaged sandbox assets: Operator experience

The operator-facing workflow for Packaged sandbox assets SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative package consumer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0049 — Packaged sandbox assets: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Packaged sandbox assets SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0061 — Packaged sandbox assets: Auditability and provenance

Every material transition and artifact produced by Packaged sandbox assets SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Packaged sandbox assets workflow and verify the packaged artifact renders the sandboxed application flow.

## SRC-MI-FEATURE-02 — List failure surfacing

Resource, tool, and prompt list failures remain visible to users and automation instead of being
swallowed as empty results.

Primary actor: **MCP developer**. Successful outcome: **transport failures preserve taxonomy and context**. Principal deliverable: **list-fetch error handling**.

### SRC-MI-STATEMENT-0002 — List failure surfacing: Core behavior

The Historical Release Replay implementation SHALL provide resource, tool, and prompt list failures remain visible to users and automation instead of being swallowed as empty results.

Acceptance intent: Demonstrate that transport failures preserve taxonomy and context; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0014 — List failure surfacing: Input and state validation

The List failure surfacing capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, an error is never misrepresented as an empty list.

### SRC-MI-STATEMENT-0026 — List failure surfacing: Interface contract

The public interfaces for List failure surfacing SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for list-fetch error handling.

### SRC-MI-STATEMENT-0038 — List failure surfacing: Operator experience

The operator-facing workflow for List failure surfacing SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative MCP developer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0050 — List failure surfacing: Authorization and least privilege

All reads, mutations, exports, and external effects associated with List failure surfacing SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0062 — List failure surfacing: Auditability and provenance

Every material transition and artifact produced by List failure surfacing SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete List failure surfacing workflow and verify transport failures preserve taxonomy and context.

## SRC-MI-FEATURE-03 — Keychain degradation

Keychain initialization failures are caught at the correct boundary and degrade to an approved
alternative rather than crashing startup.

Primary actor: **desktop user**. Successful outcome: **unsupported or failed keychain platforms remain usable with a warning**. Principal deliverable: **credential storage degradation path**.

### SRC-MI-STATEMENT-0003 — Keychain degradation: Core behavior

The Historical Release Replay implementation SHALL provide keychain initialization failures are caught at the correct boundary and degrade to an approved alternative rather than crashing startup.

Acceptance intent: Demonstrate that unsupported or failed keychain platforms remain usable with a warning; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0015 — Keychain degradation: Input and state validation

The Keychain degradation capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, secret material is not logged during fallback.

### SRC-MI-STATEMENT-0027 — Keychain degradation: Interface contract

The public interfaces for Keychain degradation SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for credential storage degradation path.

### SRC-MI-STATEMENT-0039 — Keychain degradation: Operator experience

The operator-facing workflow for Keychain degradation SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative desktop user can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0051 — Keychain degradation: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Keychain degradation SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0063 — Keychain degradation: Auditability and provenance

Every material transition and artifact produced by Keychain degradation SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Keychain degradation workflow and verify unsupported or failed keychain platforms remain usable with a warning.

## SRC-MI-FEATURE-04 — Lazy optional native loading

The optional native keyring dependency loads only when needed so unsupported platforms can start and
degrade safely.

Primary actor: **package consumer**. Successful outcome: **normal startup does not require the native module**. Principal deliverable: **lazy import boundary and tests**.

### SRC-MI-STATEMENT-0004 — Lazy optional native loading: Core behavior

The Historical Release Replay implementation SHALL provide the optional native keyring dependency loads only when needed so unsupported platforms can start and degrade safely.

Acceptance intent: Demonstrate that normal startup does not require the native module; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0016 — Lazy optional native loading: Input and state validation

The Lazy optional native loading capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, missing optional binaries do not crash unrelated clients.

### SRC-MI-STATEMENT-0028 — Lazy optional native loading: Interface contract

The public interfaces for Lazy optional native loading SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for lazy import boundary and tests.

### SRC-MI-STATEMENT-0040 — Lazy optional native loading: Operator experience

The operator-facing workflow for Lazy optional native loading SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative package consumer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0052 — Lazy optional native loading: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Lazy optional native loading SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0064 — Lazy optional native loading: Auditability and provenance

Every material transition and artifact produced by Lazy optional native loading SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Lazy optional native loading workflow and verify normal startup does not require the native module.

## SRC-MI-FEATURE-05 — Structured tool output

Tool results containing structuredContent render in the Tools screen alongside textual content with
bounded formatting.

Primary actor: **MCP developer**. Successful outcome: **structured output is visible and inspectable**. Principal deliverable: **structured result component and stories**.

### SRC-MI-STATEMENT-0005 — Structured tool output: Core behavior

The Historical Release Replay implementation SHALL provide tool results containing structuredContent render in the Tools screen alongside textual content with bounded formatting.

Acceptance intent: Demonstrate that structured output is visible and inspectable; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0017 — Structured tool output: Input and state validation

The Structured tool output capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, untrusted content cannot execute as application code.

### SRC-MI-STATEMENT-0029 — Structured tool output: Interface contract

The public interfaces for Structured tool output SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for structured result component and stories.

### SRC-MI-STATEMENT-0041 — Structured tool output: Operator experience

The operator-facing workflow for Structured tool output SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative MCP developer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0053 — Structured tool output: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Structured tool output SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0065 — Structured tool output: Auditability and provenance

Every material transition and artifact produced by Structured tool output SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Structured tool output workflow and verify structured output is visible and inspectable.

## SRC-MI-FEATURE-06 — Docker loopback and writable state

Container defaults bind safely and mounted state directories remain writable under documented user
and permission models.

Primary actor: **self-hosting operator**. Successful outcome: **default startup is reachable as documented without unsafe public exposure**. Principal deliverable: **Docker configuration and smoke test**.

### SRC-MI-STATEMENT-0006 — Docker loopback and writable state: Core behavior

The Historical Release Replay implementation SHALL provide container defaults bind safely and mounted state directories remain writable under documented user and permission models.

Acceptance intent: Demonstrate that default startup is reachable as documented without unsafe public exposure; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0018 — Docker loopback and writable state: Input and state validation

The Docker loopback and writable state capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, read-only state failures are diagnosed.

### SRC-MI-STATEMENT-0030 — Docker loopback and writable state: Interface contract

The public interfaces for Docker loopback and writable state SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for Docker configuration and smoke test.

### SRC-MI-STATEMENT-0042 — Docker loopback and writable state: Operator experience

The operator-facing workflow for Docker loopback and writable state SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative self-hosting operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0054 — Docker loopback and writable state: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Docker loopback and writable state SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0066 — Docker loopback and writable state: Auditability and provenance

Every material transition and artifact produced by Docker loopback and writable state SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Docker loopback and writable state workflow and verify default startup is reachable as documented without unsafe public exposure.

## SRC-MI-FEATURE-07 — Schema number input stability

Numeric schema fields preserve the user text while editing and validate only at appropriate commit
boundaries.

Primary actor: **MCP developer**. Successful outcome: **intermediate numeric input no longer disappears**. Principal deliverable: **number input component and interaction test**.

### SRC-MI-STATEMENT-0007 — Schema number input stability: Core behavior

The Historical Release Replay implementation SHALL provide numeric schema fields preserve the user text while editing and validate only at appropriate commit boundaries.

Acceptance intent: Demonstrate that intermediate numeric input no longer disappears; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0019 — Schema number input stability: Input and state validation

The Schema number input stability capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, invalid values remain visibly invalid rather than silently changing.

### SRC-MI-STATEMENT-0031 — Schema number input stability: Interface contract

The public interfaces for Schema number input stability SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for number input component and interaction test.

### SRC-MI-STATEMENT-0043 — Schema number input stability: Operator experience

The operator-facing workflow for Schema number input stability SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative MCP developer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0055 — Schema number input stability: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Schema number input stability SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0067 — Schema number input stability: Auditability and provenance

Every material transition and artifact produced by Schema number input stability SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Schema number input stability workflow and verify intermediate numeric input no longer disappears.

## SRC-MI-FEATURE-08 — Duplicate tool name rendering

Rows with duplicate tool names remain distinct by stable source position so filtering and selection
operate correctly.

Primary actor: **MCP developer**. Successful outcome: **every duplicate entry can be inspected independently**. Principal deliverable: **tool list identity rule and test**.

### SRC-MI-STATEMENT-0008 — Duplicate tool name rendering: Core behavior

The Historical Release Replay implementation SHALL provide rows with duplicate tool names remain distinct by stable source position so filtering and selection operate correctly.

Acceptance intent: Demonstrate that every duplicate entry can be inspected independently; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0020 — Duplicate tool name rendering: Input and state validation

The Duplicate tool name rendering capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, React key collisions do not merge or drop rows.

### SRC-MI-STATEMENT-0032 — Duplicate tool name rendering: Interface contract

The public interfaces for Duplicate tool name rendering SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for tool list identity rule and test.

### SRC-MI-STATEMENT-0044 — Duplicate tool name rendering: Operator experience

The operator-facing workflow for Duplicate tool name rendering SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative MCP developer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0056 — Duplicate tool name rendering: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Duplicate tool name rendering SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0068 — Duplicate tool name rendering: Auditability and provenance

Every material transition and artifact produced by Duplicate tool name rendering SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Duplicate tool name rendering workflow and verify every duplicate entry can be inspected independently.

## SRC-MI-FEATURE-09 — Protocol header forwarding

The negotiated protocol version and approved parameter headers propagate through the remote proxy
without forwarding excluded headers.

Primary actor: **remote client**. Successful outcome: **downstream requests observe the negotiated contract**. Principal deliverable: **proxy header policy and integration tests**.

### SRC-MI-STATEMENT-0009 — Protocol header forwarding: Core behavior

The Historical Release Replay implementation SHALL provide the negotiated protocol version and approved parameter headers propagate through the remote proxy without forwarding excluded headers.

Acceptance intent: Demonstrate that downstream requests observe the negotiated contract; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0021 — Protocol header forwarding: Input and state validation

The Protocol header forwarding capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, sensitive or disallowed headers never cross the boundary.

### SRC-MI-STATEMENT-0033 — Protocol header forwarding: Interface contract

The public interfaces for Protocol header forwarding SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for proxy header policy and integration tests.

### SRC-MI-STATEMENT-0045 — Protocol header forwarding: Operator experience

The operator-facing workflow for Protocol header forwarding SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative remote client can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0057 — Protocol header forwarding: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Protocol header forwarding SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0069 — Protocol header forwarding: Auditability and provenance

Every material transition and artifact produced by Protocol header forwarding SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Protocol header forwarding workflow and verify downstream requests observe the negotiated contract.

## SRC-MI-FEATURE-10 — Streaming compatibility

Event streams are primed and lifecycle-tested so supported browsers, including Firefox, resolve and
process event fetches consistently.

Primary actor: **web user**. Successful outcome: **stream connection reaches ready state across supported browsers**. Principal deliverable: **SSE transport fix and browser test**.

### SRC-MI-STATEMENT-0010 — Streaming compatibility: Core behavior

The Historical Release Replay implementation SHALL provide event streams are primed and lifecycle-tested so supported browsers, including Firefox, resolve and process event fetches consistently.

Acceptance intent: Demonstrate that stream connection reaches ready state across supported browsers; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0022 — Streaming compatibility: Input and state validation

The Streaming compatibility capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, tests wait on state instead of arbitrary sleeps.

### SRC-MI-STATEMENT-0034 — Streaming compatibility: Interface contract

The public interfaces for Streaming compatibility SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for SSE transport fix and browser test.

### SRC-MI-STATEMENT-0046 — Streaming compatibility: Operator experience

The operator-facing workflow for Streaming compatibility SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative web user can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0058 — Streaming compatibility: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Streaming compatibility SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0070 — Streaming compatibility: Auditability and provenance

Every material transition and artifact produced by Streaming compatibility SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Streaming compatibility workflow and verify stream connection reaches ready state across supported browsers.

## SRC-MI-FEATURE-11 — TUI dependency bundling

React rendering dependencies required by the terminal client are bundled to prevent split-React
failures in consumer installs.

Primary actor: **CLI package consumer**. Successful outcome: **packed TUI starts in a clean install**. Principal deliverable: **bundle configuration and package smoke**.

### SRC-MI-STATEMENT-0011 — TUI dependency bundling: Core behavior

The Historical Release Replay implementation SHALL provide react rendering dependencies required by the terminal client are bundled to prevent split-React failures in consumer installs.

Acceptance intent: Demonstrate that packed TUI starts in a clean install; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0023 — TUI dependency bundling: Input and state validation

The TUI dependency bundling capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, duplicate incompatible React instances are absent.

### SRC-MI-STATEMENT-0035 — TUI dependency bundling: Interface contract

The public interfaces for TUI dependency bundling SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for bundle configuration and package smoke.

### SRC-MI-STATEMENT-0047 — TUI dependency bundling: Operator experience

The operator-facing workflow for TUI dependency bundling SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative CLI package consumer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0059 — TUI dependency bundling: Authorization and least privilege

All reads, mutations, exports, and external effects associated with TUI dependency bundling SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0071 — TUI dependency bundling: Auditability and provenance

Every material transition and artifact produced by TUI dependency bundling SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete TUI dependency bundling workflow and verify packed TUI starts in a clean install.

## SRC-MI-FEATURE-12 — Release integration and documentation

Dependency alignment, deterministic tests, migration documentation, issue hygiene, CI hardening,
changelog, and package verification produce the target release.

Primary actor: **release maintainer**. Successful outcome: **all clients build, validate, smoke, and package together**. Principal deliverable: **release candidate, docs, and verification receipts**.

### SRC-MI-STATEMENT-0012 — Release integration and documentation: Core behavior

The Historical Release Replay implementation SHALL provide dependency alignment, deterministic tests, migration documentation, issue hygiene, CI hardening, changelog, and package verification produce the target release.

Acceptance intent: Demonstrate that all clients build, validate, smoke, and package together; all mandatory paths are covered by executable evidence.

### SRC-MI-STATEMENT-0024 — Release integration and documentation: Input and state validation

The Release integration and documentation capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, release completion is blocked by missing artifacts or flaky leaked timers.

### SRC-MI-STATEMENT-0036 — Release integration and documentation: Interface contract

The public interfaces for Release integration and documentation SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for release candidate, docs, and verification receipts.

### SRC-MI-STATEMENT-0048 — Release integration and documentation: Operator experience

The operator-facing workflow for Release integration and documentation SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative release maintainer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-MI-STATEMENT-0060 — Release integration and documentation: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Release integration and documentation SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-MI-STATEMENT-0072 — Release integration and documentation: Auditability and provenance

Every material transition and artifact produced by Release integration and documentation SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Release integration and documentation workflow and verify all clients build, validate, smoke, and package together.
