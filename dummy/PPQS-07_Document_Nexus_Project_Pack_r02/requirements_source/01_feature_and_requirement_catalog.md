# Document Nexus — Source Requirement Statements

The statements below are authoritative visible source material. ProjectPipeline must normalize and trace them into its own requirement and work registries.

## SRC-DN-FEATURE-01 — Conversion job submission

A versioned API accepts document conversion jobs from uploaded files, approved local references, or
test fixtures with declared output policy.

Primary actor: **application client**. Successful outcome: **valid jobs receive stable identifiers and immutable request fingerprints**. Principal deliverable: **job API and request model**.

### SRC-DN-STATEMENT-0001 — Conversion job submission: Core behavior

The Private Novel Fork implementation SHALL provide a versioned API accepts document conversion jobs from uploaded files, approved local references, or test fixtures with declared output policy.

Acceptance intent: Demonstrate that valid jobs receive stable identifiers and immutable request fingerprints; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0013 — Conversion job submission: Input and state validation

The Conversion job submission capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, duplicate or malformed submissions do not create duplicate work.

### SRC-DN-STATEMENT-0025 — Conversion job submission: Interface contract

The public interfaces for Conversion job submission SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for job API and request model.

### SRC-DN-STATEMENT-0037 — Conversion job submission: Operator experience

The operator-facing workflow for Conversion job submission SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative application client can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0049 — Conversion job submission: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Conversion job submission SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0061 — Conversion job submission: Auditability and provenance

Every material transition and artifact produced by Conversion job submission SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Conversion job submission workflow and verify valid jobs receive stable identifiers and immutable request fingerprints.

### SRC-DN-STATEMENT-0073 — Conversion job submission: Failure handling

The Conversion job submission capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when duplicate or malformed submissions do not create duplicate work.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0085 — Conversion job submission: Idempotency and concurrency

Commands and operations for Conversion job submission SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0097 — Conversion job submission: Performance and resource bounds

The Conversion job submission implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0109 — Conversion job submission: Verification and regression protection

The Conversion job submission capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0121 — Conversion job submission: Observability and diagnostics

The Conversion job submission capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Conversion job submission from supported diagnostics.

### SRC-DN-STATEMENT-0133 — Conversion job submission: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Conversion job submission.

Acceptance intent: A clean operator can reproduce the documented Conversion job submission workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-02 — Source adapter boundary

Source adapters isolate acquisition from conversion and enforce size, type, path, URL, timeout, and
allowlist policy.

Primary actor: **integration developer**. Successful outcome: **approved sources become immutable input artifacts**. Principal deliverable: **adapter interface and approved adapters**.

### SRC-DN-STATEMENT-0002 — Source adapter boundary: Core behavior

The Private Novel Fork implementation SHALL provide source adapters isolate acquisition from conversion and enforce size, type, path, URL, timeout, and allowlist policy.

Acceptance intent: Demonstrate that approved sources become immutable input artifacts; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0014 — Source adapter boundary: Input and state validation

The Source adapter boundary capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, path traversal, SSRF, and unsupported media are blocked.

### SRC-DN-STATEMENT-0026 — Source adapter boundary: Interface contract

The public interfaces for Source adapter boundary SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for adapter interface and approved adapters.

### SRC-DN-STATEMENT-0038 — Source adapter boundary: Operator experience

The operator-facing workflow for Source adapter boundary SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative integration developer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0050 — Source adapter boundary: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Source adapter boundary SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0062 — Source adapter boundary: Auditability and provenance

Every material transition and artifact produced by Source adapter boundary SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Source adapter boundary workflow and verify approved sources become immutable input artifacts.

### SRC-DN-STATEMENT-0074 — Source adapter boundary: Failure handling

The Source adapter boundary capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when path traversal, SSRF, and unsupported media are blocked.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0086 — Source adapter boundary: Idempotency and concurrency

Commands and operations for Source adapter boundary SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0098 — Source adapter boundary: Performance and resource bounds

The Source adapter boundary implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0110 — Source adapter boundary: Verification and regression protection

The Source adapter boundary capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0122 — Source adapter boundary: Observability and diagnostics

The Source adapter boundary capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Source adapter boundary from supported diagnostics.

### SRC-DN-STATEMENT-0134 — Source adapter boundary: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Source adapter boundary.

Acceptance intent: A clean operator can reproduce the documented Source adapter boundary workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-03 — Conversion worker integration

Workers invoke the pinned document-conversion library through a narrow adapter with timeout,
cancellation, version capture, and bounded output.

Primary actor: **worker**. Successful outcome: **conversion results are attributable to exact engine versions**. Principal deliverable: **conversion adapter and worker**.

### SRC-DN-STATEMENT-0003 — Conversion worker integration: Core behavior

The Private Novel Fork implementation SHALL provide workers invoke the pinned document-conversion library through a narrow adapter with timeout, cancellation, version capture, and bounded output.

Acceptance intent: Demonstrate that conversion results are attributable to exact engine versions; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0015 — Conversion worker integration: Input and state validation

The Conversion worker integration capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, worker failure never marks a job complete.

### SRC-DN-STATEMENT-0027 — Conversion worker integration: Interface contract

The public interfaces for Conversion worker integration SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for conversion adapter and worker.

### SRC-DN-STATEMENT-0039 — Conversion worker integration: Operator experience

The operator-facing workflow for Conversion worker integration SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative worker can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0051 — Conversion worker integration: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Conversion worker integration SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0063 — Conversion worker integration: Auditability and provenance

Every material transition and artifact produced by Conversion worker integration SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Conversion worker integration workflow and verify conversion results are attributable to exact engine versions.

### SRC-DN-STATEMENT-0075 — Conversion worker integration: Failure handling

The Conversion worker integration capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when worker failure never marks a job complete.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0087 — Conversion worker integration: Idempotency and concurrency

Commands and operations for Conversion worker integration SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0099 — Conversion worker integration: Performance and resource bounds

The Conversion worker integration implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0111 — Conversion worker integration: Verification and regression protection

The Conversion worker integration capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0123 — Conversion worker integration: Observability and diagnostics

The Conversion worker integration capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Conversion worker integration from supported diagnostics.

### SRC-DN-STATEMENT-0135 — Conversion worker integration: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Conversion worker integration.

Acceptance intent: A clean operator can reproduce the documented Conversion worker integration workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-04 — Artifact storage

Input, output, logs, and manifests use content-addressed local storage with retention, checksums,
atomic publication, and download authorization.

Primary actor: **operator**. Successful outcome: **published artifacts verify against their manifests**. Principal deliverable: **artifact store and manifest schema**.

### SRC-DN-STATEMENT-0004 — Artifact storage: Core behavior

The Private Novel Fork implementation SHALL provide input, output, logs, and manifests use content-addressed local storage with retention, checksums, atomic publication, and download authorization.

Acceptance intent: Demonstrate that published artifacts verify against their manifests; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0016 — Artifact storage: Input and state validation

The Artifact storage capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, partial or tampered artifacts are quarantined.

### SRC-DN-STATEMENT-0028 — Artifact storage: Interface contract

The public interfaces for Artifact storage SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for artifact store and manifest schema.

### SRC-DN-STATEMENT-0040 — Artifact storage: Operator experience

The operator-facing workflow for Artifact storage SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0052 — Artifact storage: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Artifact storage SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0064 — Artifact storage: Auditability and provenance

Every material transition and artifact produced by Artifact storage SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Artifact storage workflow and verify published artifacts verify against their manifests.

### SRC-DN-STATEMENT-0076 — Artifact storage: Failure handling

The Artifact storage capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when partial or tampered artifacts are quarantined.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0088 — Artifact storage: Idempotency and concurrency

Commands and operations for Artifact storage SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0100 — Artifact storage: Performance and resource bounds

The Artifact storage implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0112 — Artifact storage: Verification and regression protection

The Artifact storage capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0124 — Artifact storage: Observability and diagnostics

The Artifact storage capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Artifact storage from supported diagnostics.

### SRC-DN-STATEMENT-0136 — Artifact storage: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Artifact storage.

Acceptance intent: A clean operator can reproduce the documented Artifact storage workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-05 — Plugin allowlist

Optional conversion plugins are disabled by default and can run only when pinned, allowlisted,
provenance-verified, and permitted for the tenant.

Primary actor: **security administrator**. Successful outcome: **approved plugins are explicit and observable**. Principal deliverable: **plugin policy and registry**.

### SRC-DN-STATEMENT-0005 — Plugin allowlist: Core behavior

The Private Novel Fork implementation SHALL provide optional conversion plugins are disabled by default and can run only when pinned, allowlisted, provenance-verified, and permitted for the tenant.

Acceptance intent: Demonstrate that approved plugins are explicit and observable; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0017 — Plugin allowlist: Input and state validation

The Plugin allowlist capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, project documents cannot self-enable plugins.

### SRC-DN-STATEMENT-0029 — Plugin allowlist: Interface contract

The public interfaces for Plugin allowlist SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for plugin policy and registry.

### SRC-DN-STATEMENT-0041 — Plugin allowlist: Operator experience

The operator-facing workflow for Plugin allowlist SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative security administrator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0053 — Plugin allowlist: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Plugin allowlist SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0065 — Plugin allowlist: Auditability and provenance

Every material transition and artifact produced by Plugin allowlist SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Plugin allowlist workflow and verify approved plugins are explicit and observable.

### SRC-DN-STATEMENT-0077 — Plugin allowlist: Failure handling

The Plugin allowlist capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when project documents cannot self-enable plugins.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0089 — Plugin allowlist: Idempotency and concurrency

Commands and operations for Plugin allowlist SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0101 — Plugin allowlist: Performance and resource bounds

The Plugin allowlist implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0113 — Plugin allowlist: Verification and regression protection

The Plugin allowlist capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0125 — Plugin allowlist: Observability and diagnostics

The Plugin allowlist capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Plugin allowlist from supported diagnostics.

### SRC-DN-STATEMENT-0137 — Plugin allowlist: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Plugin allowlist.

Acceptance intent: A clean operator can reproduce the documented Plugin allowlist workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-06 — Redaction policy

Configurable redaction detects and removes declared sensitive patterns from converted output,
previews, logs, and support bundles before publication.

Primary actor: **compliance operator**. Successful outcome: **redaction findings are counted without exposing matched secrets**. Principal deliverable: **redaction engine and report**.

### SRC-DN-STATEMENT-0006 — Redaction policy: Core behavior

The Private Novel Fork implementation SHALL provide configurable redaction detects and removes declared sensitive patterns from converted output, previews, logs, and support bundles before publication.

Acceptance intent: Demonstrate that redaction findings are counted without exposing matched secrets; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0018 — Redaction policy: Input and state validation

The Redaction policy capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, raw sensitive content does not cross an unauthorized boundary.

### SRC-DN-STATEMENT-0030 — Redaction policy: Interface contract

The public interfaces for Redaction policy SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for redaction engine and report.

### SRC-DN-STATEMENT-0042 — Redaction policy: Operator experience

The operator-facing workflow for Redaction policy SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative compliance operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0054 — Redaction policy: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Redaction policy SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0066 — Redaction policy: Auditability and provenance

Every material transition and artifact produced by Redaction policy SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Redaction policy workflow and verify redaction findings are counted without exposing matched secrets.

### SRC-DN-STATEMENT-0078 — Redaction policy: Failure handling

The Redaction policy capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when raw sensitive content does not cross an unauthorized boundary.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0090 — Redaction policy: Idempotency and concurrency

Commands and operations for Redaction policy SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0102 — Redaction policy: Performance and resource bounds

The Redaction policy implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0114 — Redaction policy: Verification and regression protection

The Redaction policy capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0126 — Redaction policy: Observability and diagnostics

The Redaction policy capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Redaction policy from supported diagnostics.

### SRC-DN-STATEMENT-0138 — Redaction policy: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Redaction policy.

Acceptance intent: A clean operator can reproduce the documented Redaction policy workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-07 — Content safety and untrusted instructions

Converted content is treated as untrusted data and cannot change agent, tool, security, Jira, or
benchmark authority.

Primary actor: **automation operator**. Successful outcome: **prompt-like document text remains inert content**. Principal deliverable: **trust labels and context firewall integration**.

### SRC-DN-STATEMENT-0007 — Content safety and untrusted instructions: Core behavior

The Private Novel Fork implementation SHALL provide converted content is treated as untrusted data and cannot change agent, tool, security, Jira, or benchmark authority.

Acceptance intent: Demonstrate that prompt-like document text remains inert content; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0019 — Content safety and untrusted instructions: Input and state validation

The Content safety and untrusted instructions capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, instruction injection cannot trigger external mutation.

### SRC-DN-STATEMENT-0031 — Content safety and untrusted instructions: Interface contract

The public interfaces for Content safety and untrusted instructions SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for trust labels and context firewall integration.

### SRC-DN-STATEMENT-0043 — Content safety and untrusted instructions: Operator experience

The operator-facing workflow for Content safety and untrusted instructions SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative automation operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0055 — Content safety and untrusted instructions: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Content safety and untrusted instructions SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0067 — Content safety and untrusted instructions: Auditability and provenance

Every material transition and artifact produced by Content safety and untrusted instructions SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Content safety and untrusted instructions workflow and verify prompt-like document text remains inert content.

### SRC-DN-STATEMENT-0079 — Content safety and untrusted instructions: Failure handling

The Content safety and untrusted instructions capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when instruction injection cannot trigger external mutation.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0091 — Content safety and untrusted instructions: Idempotency and concurrency

Commands and operations for Content safety and untrusted instructions SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0103 — Content safety and untrusted instructions: Performance and resource bounds

The Content safety and untrusted instructions implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0115 — Content safety and untrusted instructions: Verification and regression protection

The Content safety and untrusted instructions capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0127 — Content safety and untrusted instructions: Observability and diagnostics

The Content safety and untrusted instructions capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Content safety and untrusted instructions from supported diagnostics.

### SRC-DN-STATEMENT-0139 — Content safety and untrusted instructions: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Content safety and untrusted instructions.

Acceptance intent: A clean operator can reproduce the documented Content safety and untrusted instructions workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-08 — Retry idempotency and recovery

Jobs use idempotency keys, leases, checkpoints, bounded retry, dead-letter state, and restart-safe
recovery.

Primary actor: **operations engineer**. Successful outcome: **a crash or provider outage resumes exactly once**. Principal deliverable: **job state machine and recovery worker**.

### SRC-DN-STATEMENT-0008 — Retry idempotency and recovery: Core behavior

The Private Novel Fork implementation SHALL provide jobs use idempotency keys, leases, checkpoints, bounded retry, dead-letter state, and restart-safe recovery.

Acceptance intent: Demonstrate that a crash or provider outage resumes exactly once; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0020 — Retry idempotency and recovery: Input and state validation

The Retry idempotency and recovery capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unknown result and duplicate delivery cannot publish conflicting artifacts.

### SRC-DN-STATEMENT-0032 — Retry idempotency and recovery: Interface contract

The public interfaces for Retry idempotency and recovery SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for job state machine and recovery worker.

### SRC-DN-STATEMENT-0044 — Retry idempotency and recovery: Operator experience

The operator-facing workflow for Retry idempotency and recovery SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative operations engineer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0056 — Retry idempotency and recovery: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Retry idempotency and recovery SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0068 — Retry idempotency and recovery: Auditability and provenance

Every material transition and artifact produced by Retry idempotency and recovery SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Retry idempotency and recovery workflow and verify a crash or provider outage resumes exactly once.

### SRC-DN-STATEMENT-0080 — Retry idempotency and recovery: Failure handling

The Retry idempotency and recovery capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when unknown result and duplicate delivery cannot publish conflicting artifacts.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0092 — Retry idempotency and recovery: Idempotency and concurrency

Commands and operations for Retry idempotency and recovery SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0104 — Retry idempotency and recovery: Performance and resource bounds

The Retry idempotency and recovery implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0116 — Retry idempotency and recovery: Verification and regression protection

The Retry idempotency and recovery capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0128 — Retry idempotency and recovery: Observability and diagnostics

The Retry idempotency and recovery capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Retry idempotency and recovery from supported diagnostics.

### SRC-DN-STATEMENT-0140 — Retry idempotency and recovery: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Retry idempotency and recovery.

Acceptance intent: A clean operator can reproduce the documented Retry idempotency and recovery workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-09 — Audit provenance and evidence

Every transition records actor, source hash, engine version, policy version, artifacts, test
evidence, and correlation identifiers.

Primary actor: **auditor**. Successful outcome: **the complete lineage is exportable and tamper-evident**. Principal deliverable: **audit ledger and evidence export**.

### SRC-DN-STATEMENT-0009 — Audit provenance and evidence: Core behavior

The Private Novel Fork implementation SHALL provide every transition records actor, source hash, engine version, policy version, artifacts, test evidence, and correlation identifiers.

Acceptance intent: Demonstrate that the complete lineage is exportable and tamper-evident; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0021 — Audit provenance and evidence: Input and state validation

The Audit provenance and evidence capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, missing evidence prevents final completion.

### SRC-DN-STATEMENT-0033 — Audit provenance and evidence: Interface contract

The public interfaces for Audit provenance and evidence SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for audit ledger and evidence export.

### SRC-DN-STATEMENT-0045 — Audit provenance and evidence: Operator experience

The operator-facing workflow for Audit provenance and evidence SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative auditor can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0057 — Audit provenance and evidence: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Audit provenance and evidence SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0069 — Audit provenance and evidence: Auditability and provenance

Every material transition and artifact produced by Audit provenance and evidence SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Audit provenance and evidence workflow and verify the complete lineage is exportable and tamper-evident.

### SRC-DN-STATEMENT-0081 — Audit provenance and evidence: Failure handling

The Audit provenance and evidence capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when missing evidence prevents final completion.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0093 — Audit provenance and evidence: Idempotency and concurrency

Commands and operations for Audit provenance and evidence SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0105 — Audit provenance and evidence: Performance and resource bounds

The Audit provenance and evidence implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0117 — Audit provenance and evidence: Verification and regression protection

The Audit provenance and evidence capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0129 — Audit provenance and evidence: Observability and diagnostics

The Audit provenance and evidence capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Audit provenance and evidence from supported diagnostics.

### SRC-DN-STATEMENT-0141 — Audit provenance and evidence: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Audit provenance and evidence.

Acceptance intent: A clean operator can reproduce the documented Audit provenance and evidence workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-10 — Operator dashboard

A responsive TypeScript web console shows queues, job details, previews, failures, policy findings,
artifacts, retries, and evidence.

Primary actor: **operator**. Successful outcome: **critical workflows are keyboard accessible and freshness-labeled**. Principal deliverable: **web console and browser tests**.

### SRC-DN-STATEMENT-0010 — Operator dashboard: Core behavior

The Private Novel Fork implementation SHALL provide a responsive TypeScript web console shows queues, job details, previews, failures, policy findings, artifacts, retries, and evidence.

Acceptance intent: Demonstrate that critical workflows are keyboard accessible and freshness-labeled; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0022 — Operator dashboard: Input and state validation

The Operator dashboard capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, UI state never overrides backend truth.

### SRC-DN-STATEMENT-0034 — Operator dashboard: Interface contract

The public interfaces for Operator dashboard SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for web console and browser tests.

### SRC-DN-STATEMENT-0046 — Operator dashboard: Operator experience

The operator-facing workflow for Operator dashboard SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0058 — Operator dashboard: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Operator dashboard SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0070 — Operator dashboard: Auditability and provenance

Every material transition and artifact produced by Operator dashboard SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Operator dashboard workflow and verify critical workflows are keyboard accessible and freshness-labeled.

### SRC-DN-STATEMENT-0082 — Operator dashboard: Failure handling

The Operator dashboard capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when UI state never overrides backend truth.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0094 — Operator dashboard: Idempotency and concurrency

Commands and operations for Operator dashboard SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0106 — Operator dashboard: Performance and resource bounds

The Operator dashboard implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0118 — Operator dashboard: Verification and regression protection

The Operator dashboard capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0130 — Operator dashboard: Observability and diagnostics

The Operator dashboard capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Operator dashboard from supported diagnostics.

### SRC-DN-STATEMENT-0142 — Operator dashboard: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Operator dashboard.

Acceptance intent: A clean operator can reproduce the documented Operator dashboard workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-11 — Webhooks and events

Signed webhooks and a polling API publish job lifecycle events with replay protection, delivery
receipts, retries, and a mock receiver.

Primary actor: **integration client**. Successful outcome: **events reconcile to the audit ledger**. Principal deliverable: **outbox, webhook sender, and mock service**.

### SRC-DN-STATEMENT-0011 — Webhooks and events: Core behavior

The Private Novel Fork implementation SHALL provide signed webhooks and a polling API publish job lifecycle events with replay protection, delivery receipts, retries, and a mock receiver.

Acceptance intent: Demonstrate that events reconcile to the audit ledger; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0023 — Webhooks and events: Input and state validation

The Webhooks and events capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, provider outage does not lose events or expose payloads.

### SRC-DN-STATEMENT-0035 — Webhooks and events: Interface contract

The public interfaces for Webhooks and events SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for outbox, webhook sender, and mock service.

### SRC-DN-STATEMENT-0047 — Webhooks and events: Operator experience

The operator-facing workflow for Webhooks and events SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative integration client can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0059 — Webhooks and events: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Webhooks and events SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0071 — Webhooks and events: Auditability and provenance

Every material transition and artifact produced by Webhooks and events SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Webhooks and events workflow and verify events reconcile to the audit ledger.

### SRC-DN-STATEMENT-0083 — Webhooks and events: Failure handling

The Webhooks and events capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when provider outage does not lose events or expose payloads.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0095 — Webhooks and events: Idempotency and concurrency

Commands and operations for Webhooks and events SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0107 — Webhooks and events: Performance and resource bounds

The Webhooks and events implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0119 — Webhooks and events: Verification and regression protection

The Webhooks and events capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0131 — Webhooks and events: Observability and diagnostics

The Webhooks and events capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Webhooks and events from supported diagnostics.

### SRC-DN-STATEMENT-0143 — Webhooks and events: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Webhooks and events.

Acceptance intent: A clean operator can reproduce the documented Webhooks and events workflow and the commands agree with the shipped code.

## SRC-DN-FEATURE-12 — Tenancy RBAC deployment and handoff

Tenant isolation, RBAC, environment validation, Docker runtime, health, metrics, backups, upgrade,
rollback, documentation, and release evidence support operation.

Primary actor: **platform administrator**. Successful outcome: **a clean deployment is reproducible and tenant boundaries are tested**. Principal deliverable: **security policy, containers, runbooks, and release bundle**.

### SRC-DN-STATEMENT-0012 — Tenancy RBAC deployment and handoff: Core behavior

The Private Novel Fork implementation SHALL provide tenant isolation, RBAC, environment validation, Docker runtime, health, metrics, backups, upgrade, rollback, documentation, and release evidence support operation.

Acceptance intent: Demonstrate that a clean deployment is reproducible and tenant boundaries are tested; all mandatory paths are covered by executable evidence.

### SRC-DN-STATEMENT-0024 — Tenancy RBAC deployment and handoff: Input and state validation

The Tenancy RBAC deployment and handoff capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unsafe defaults and missing configuration block startup.

### SRC-DN-STATEMENT-0036 — Tenancy RBAC deployment and handoff: Interface contract

The public interfaces for Tenancy RBAC deployment and handoff SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for security policy, containers, runbooks, and release bundle.

### SRC-DN-STATEMENT-0048 — Tenancy RBAC deployment and handoff: Operator experience

The operator-facing workflow for Tenancy RBAC deployment and handoff SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative platform administrator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DN-STATEMENT-0060 — Tenancy RBAC deployment and handoff: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Tenancy RBAC deployment and handoff SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DN-STATEMENT-0072 — Tenancy RBAC deployment and handoff: Auditability and provenance

Every material transition and artifact produced by Tenancy RBAC deployment and handoff SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Tenancy RBAC deployment and handoff workflow and verify a clean deployment is reproducible and tenant boundaries are tested.

### SRC-DN-STATEMENT-0084 — Tenancy RBAC deployment and handoff: Failure handling

The Tenancy RBAC deployment and handoff capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when unsafe defaults and missing configuration block startup.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DN-STATEMENT-0096 — Tenancy RBAC deployment and handoff: Idempotency and concurrency

Commands and operations for Tenancy RBAC deployment and handoff SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DN-STATEMENT-0108 — Tenancy RBAC deployment and handoff: Performance and resource bounds

The Tenancy RBAC deployment and handoff implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DN-STATEMENT-0120 — Tenancy RBAC deployment and handoff: Verification and regression protection

The Tenancy RBAC deployment and handoff capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

### SRC-DN-STATEMENT-0132 — Tenancy RBAC deployment and handoff: Observability and diagnostics

The Tenancy RBAC deployment and handoff capability SHALL expose structured logs, health or status signals, correlation identifiers, and failure diagnostics without emitting protected content.

Acceptance intent: Operators can identify current state, freshness, failure cause, and recovery action for Tenancy RBAC deployment and handoff from supported diagnostics.

### SRC-DN-STATEMENT-0144 — Tenancy RBAC deployment and handoff: Documentation and handoff

The final project SHALL document installation, configuration, architecture, operation, testing, failure recovery, security boundaries, and supported use of Tenancy RBAC deployment and handoff.

Acceptance intent: A clean operator can reproduce the documented Tenancy RBAC deployment and handoff workflow and the commands agree with the shipped code.
