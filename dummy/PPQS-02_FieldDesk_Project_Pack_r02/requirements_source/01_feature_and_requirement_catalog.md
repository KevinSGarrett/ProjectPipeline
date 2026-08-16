# FieldDesk — Source Requirement Statements

The statements below are authoritative visible source material. ProjectPipeline must normalize and trace them into its own requirement and work registries.

## SRC-FD-FEATURE-01 — Identity and sessions

Local development identity plus production-ready session boundaries support administrators,
dispatchers, technicians, and read-only auditors.

Primary actor: **authenticated user**. Successful outcome: **identity is established and expired sessions are rejected**. Principal deliverable: **identity service, session middleware, and login UI**.

### SRC-FD-STATEMENT-0001 — Identity and sessions: Core behavior

The FieldDesk implementation SHALL provide local development identity plus production-ready session boundaries support administrators, dispatchers, technicians, and read-only auditors.

Acceptance intent: Demonstrate that identity is established and expired sessions are rejected; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0013 — Identity and sessions: Input and state validation

The Identity and sessions capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unauthenticated and cross-tenant access is denied.

### SRC-FD-STATEMENT-0025 — Identity and sessions: Interface contract

The public interfaces for Identity and sessions SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for identity service, session middleware, and login UI.

### SRC-FD-STATEMENT-0037 — Identity and sessions: Operator experience

The operator-facing workflow for Identity and sessions SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative authenticated user can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0049 — Identity and sessions: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Identity and sessions SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0061 — Identity and sessions: Auditability and provenance

Every material transition and artifact produced by Identity and sessions SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Identity and sessions workflow and verify identity is established and expired sessions are rejected.

### SRC-FD-STATEMENT-0073 — Identity and sessions: Failure handling

The Identity and sessions capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when unauthenticated and cross-tenant access is denied.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0085 — Identity and sessions: Idempotency and concurrency

Commands and operations for Identity and sessions SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0097 — Identity and sessions: Performance and resource bounds

The Identity and sessions implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-02 — Role based access control

Permissions are enforced consistently across API routes, UI affordances, exports, and background
operations.

Primary actor: **administrator**. Successful outcome: **each role can perform exactly its authorized actions**. Principal deliverable: **RBAC policy and authorization tests**.

### SRC-FD-STATEMENT-0002 — Role based access control: Core behavior

The FieldDesk implementation SHALL provide permissions are enforced consistently across API routes, UI affordances, exports, and background operations.

Acceptance intent: Demonstrate that each role can perform exactly its authorized actions; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0014 — Role based access control: Input and state validation

The Role based access control capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, privilege escalation and UI-only enforcement are impossible.

### SRC-FD-STATEMENT-0026 — Role based access control: Interface contract

The public interfaces for Role based access control SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for RBAC policy and authorization tests.

### SRC-FD-STATEMENT-0038 — Role based access control: Operator experience

The operator-facing workflow for Role based access control SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative administrator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0050 — Role based access control: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Role based access control SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0062 — Role based access control: Auditability and provenance

Every material transition and artifact produced by Role based access control SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Role based access control workflow and verify each role can perform exactly its authorized actions.

### SRC-FD-STATEMENT-0074 — Role based access control: Failure handling

The Role based access control capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when privilege escalation and UI-only enforcement are impossible.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0086 — Role based access control: Idempotency and concurrency

Commands and operations for Role based access control SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0098 — Role based access control: Performance and resource bounds

The Role based access control implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-03 — Customers and locations

Customer accounts contain one or more service locations with contacts, operating windows, access
instructions, and status.

Primary actor: **dispatcher**. Successful outcome: **valid location records are searchable and auditable**. Principal deliverable: **customer and location domain modules**.

### SRC-FD-STATEMENT-0003 — Customers and locations: Core behavior

The FieldDesk implementation SHALL provide customer accounts contain one or more service locations with contacts, operating windows, access instructions, and status.

Acceptance intent: Demonstrate that valid location records are searchable and auditable; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0015 — Customers and locations: Input and state validation

The Customers and locations capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, invalid addresses and orphan locations are rejected.

### SRC-FD-STATEMENT-0027 — Customers and locations: Interface contract

The public interfaces for Customers and locations SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for customer and location domain modules.

### SRC-FD-STATEMENT-0039 — Customers and locations: Operator experience

The operator-facing workflow for Customers and locations SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative dispatcher can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0051 — Customers and locations: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Customers and locations SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0063 — Customers and locations: Auditability and provenance

Every material transition and artifact produced by Customers and locations SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Customers and locations workflow and verify valid location records are searchable and auditable.

### SRC-FD-STATEMENT-0075 — Customers and locations: Failure handling

The Customers and locations capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when invalid addresses and orphan locations are rejected.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0087 — Customers and locations: Idempotency and concurrency

Commands and operations for Customers and locations SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0099 — Customers and locations: Performance and resource bounds

The Customers and locations implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-04 — Technicians and skills

Technician profiles capture availability, skills, certifications, service radius, active status, and
assignment eligibility.

Primary actor: **service manager**. Successful outcome: **eligible technicians can be selected deterministically**. Principal deliverable: **technician profile and eligibility engine**.

### SRC-FD-STATEMENT-0004 — Technicians and skills: Core behavior

The FieldDesk implementation SHALL provide technician profiles capture availability, skills, certifications, service radius, active status, and assignment eligibility.

Acceptance intent: Demonstrate that eligible technicians can be selected deterministically; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0016 — Technicians and skills: Input and state validation

The Technicians and skills capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, expired certification and inactive status prevent assignment.

### SRC-FD-STATEMENT-0028 — Technicians and skills: Interface contract

The public interfaces for Technicians and skills SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for technician profile and eligibility engine.

### SRC-FD-STATEMENT-0040 — Technicians and skills: Operator experience

The operator-facing workflow for Technicians and skills SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative service manager can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0052 — Technicians and skills: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Technicians and skills SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0064 — Technicians and skills: Auditability and provenance

Every material transition and artifact produced by Technicians and skills SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Technicians and skills workflow and verify eligible technicians can be selected deterministically.

### SRC-FD-STATEMENT-0076 — Technicians and skills: Failure handling

The Technicians and skills capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when expired certification and inactive status prevent assignment.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0088 — Technicians and skills: Idempotency and concurrency

Commands and operations for Technicians and skills SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0100 — Technicians and skills: Performance and resource bounds

The Technicians and skills implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-05 — Work order lifecycle

Work orders support draft, scheduled, dispatched, in-progress, blocked, completed, cancelled, and
reopened states with guarded transitions.

Primary actor: **dispatcher**. Successful outcome: **every allowed transition records actor, timestamp, reason, and prior state**. Principal deliverable: **work-order aggregate and lifecycle policy**.

### SRC-FD-STATEMENT-0005 — Work order lifecycle: Core behavior

The FieldDesk implementation SHALL provide work orders support draft, scheduled, dispatched, in-progress, blocked, completed, cancelled, and reopened states with guarded transitions.

Acceptance intent: Demonstrate that every allowed transition records actor, timestamp, reason, and prior state; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0017 — Work order lifecycle: Input and state validation

The Work order lifecycle capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, invalid transitions fail atomically.

### SRC-FD-STATEMENT-0029 — Work order lifecycle: Interface contract

The public interfaces for Work order lifecycle SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for work-order aggregate and lifecycle policy.

### SRC-FD-STATEMENT-0041 — Work order lifecycle: Operator experience

The operator-facing workflow for Work order lifecycle SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative dispatcher can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0053 — Work order lifecycle: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Work order lifecycle SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0065 — Work order lifecycle: Auditability and provenance

Every material transition and artifact produced by Work order lifecycle SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Work order lifecycle workflow and verify every allowed transition records actor, timestamp, reason, and prior state.

### SRC-FD-STATEMENT-0077 — Work order lifecycle: Failure handling

The Work order lifecycle capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when invalid transitions fail atomically.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0089 — Work order lifecycle: Idempotency and concurrency

Commands and operations for Work order lifecycle SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0101 — Work order lifecycle: Performance and resource bounds

The Work order lifecycle implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-06 — Assignment and scheduling

Assignments enforce technician eligibility, location windows, overlap rules, optimistic concurrency,
and reassignment history.

Primary actor: **dispatcher**. Successful outcome: **conflict-free assignments are created and changed safely**. Principal deliverable: **scheduling service and calendar UI**.

### SRC-FD-STATEMENT-0006 — Assignment and scheduling: Core behavior

The FieldDesk implementation SHALL provide assignments enforce technician eligibility, location windows, overlap rules, optimistic concurrency, and reassignment history.

Acceptance intent: Demonstrate that conflict-free assignments are created and changed safely; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0018 — Assignment and scheduling: Input and state validation

The Assignment and scheduling capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, overlaps and stale updates are rejected with actionable conflicts.

### SRC-FD-STATEMENT-0030 — Assignment and scheduling: Interface contract

The public interfaces for Assignment and scheduling SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for scheduling service and calendar UI.

### SRC-FD-STATEMENT-0042 — Assignment and scheduling: Operator experience

The operator-facing workflow for Assignment and scheduling SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative dispatcher can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0054 — Assignment and scheduling: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Assignment and scheduling SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0066 — Assignment and scheduling: Auditability and provenance

Every material transition and artifact produced by Assignment and scheduling SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Assignment and scheduling workflow and verify conflict-free assignments are created and changed safely.

### SRC-FD-STATEMENT-0078 — Assignment and scheduling: Failure handling

The Assignment and scheduling capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when overlaps and stale updates are rejected with actionable conflicts.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0090 — Assignment and scheduling: Idempotency and concurrency

Commands and operations for Assignment and scheduling SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0102 — Assignment and scheduling: Performance and resource bounds

The Assignment and scheduling implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-07 — Comments and attachments

Users can add threaded comments and attachment metadata subject to size, type, authorization, and
retention rules.

Primary actor: **technician**. Successful outcome: **authorized collaboration is visible in chronological context**. Principal deliverable: **comment and attachment modules**.

### SRC-FD-STATEMENT-0007 — Comments and attachments: Core behavior

The FieldDesk implementation SHALL provide users can add threaded comments and attachment metadata subject to size, type, authorization, and retention rules.

Acceptance intent: Demonstrate that authorized collaboration is visible in chronological context; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0019 — Comments and attachments: Input and state validation

The Comments and attachments capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, malicious metadata and unauthorized downloads are blocked.

### SRC-FD-STATEMENT-0031 — Comments and attachments: Interface contract

The public interfaces for Comments and attachments SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for comment and attachment modules.

### SRC-FD-STATEMENT-0043 — Comments and attachments: Operator experience

The operator-facing workflow for Comments and attachments SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative technician can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0055 — Comments and attachments: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Comments and attachments SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0067 — Comments and attachments: Auditability and provenance

Every material transition and artifact produced by Comments and attachments SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Comments and attachments workflow and verify authorized collaboration is visible in chronological context.

### SRC-FD-STATEMENT-0079 — Comments and attachments: Failure handling

The Comments and attachments capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when malicious metadata and unauthorized downloads are blocked.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0091 — Comments and attachments: Idempotency and concurrency

Commands and operations for Comments and attachments SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0103 — Comments and attachments: Performance and resource bounds

The Comments and attachments implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-08 — Audit history

Immutable audit events capture security-sensitive and business-critical state changes with
correlation identifiers.

Primary actor: **auditor**. Successful outcome: **events can reconstruct the history of every work order**. Principal deliverable: **audit ledger, viewer, and export**.

### SRC-FD-STATEMENT-0008 — Audit history: Core behavior

The FieldDesk implementation SHALL provide immutable audit events capture security-sensitive and business-critical state changes with correlation identifiers.

Acceptance intent: Demonstrate that events can reconstruct the history of every work order; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0020 — Audit history: Input and state validation

The Audit history capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, events cannot be edited through product APIs.

### SRC-FD-STATEMENT-0032 — Audit history: Interface contract

The public interfaces for Audit history SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for audit ledger, viewer, and export.

### SRC-FD-STATEMENT-0044 — Audit history: Operator experience

The operator-facing workflow for Audit history SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative auditor can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0056 — Audit history: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Audit history SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0068 — Audit history: Auditability and provenance

Every material transition and artifact produced by Audit history SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Audit history workflow and verify events can reconstruct the history of every work order.

### SRC-FD-STATEMENT-0080 — Audit history: Failure handling

The Audit history capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when events cannot be edited through product APIs.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0092 — Audit history: Idempotency and concurrency

Commands and operations for Audit history SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0104 — Audit history: Performance and resource bounds

The Audit history implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-09 — Search filtering and pagination

Users can search and filter work orders by status, dates, priority, customer, location, assignee,
and text with stable pagination.

Primary actor: **dispatcher**. Successful outcome: **queries return deterministic ordered results and preserved filter state**. Principal deliverable: **search API and filter UI**.

### SRC-FD-STATEMENT-0009 — Search filtering and pagination: Core behavior

The FieldDesk implementation SHALL provide users can search and filter work orders by status, dates, priority, customer, location, assignee, and text with stable pagination.

Acceptance intent: Demonstrate that queries return deterministic ordered results and preserved filter state; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0021 — Search filtering and pagination: Input and state validation

The Search filtering and pagination capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unbounded scans and injection are prevented.

### SRC-FD-STATEMENT-0033 — Search filtering and pagination: Interface contract

The public interfaces for Search filtering and pagination SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for search API and filter UI.

### SRC-FD-STATEMENT-0045 — Search filtering and pagination: Operator experience

The operator-facing workflow for Search filtering and pagination SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative dispatcher can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0057 — Search filtering and pagination: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Search filtering and pagination SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0069 — Search filtering and pagination: Auditability and provenance

Every material transition and artifact produced by Search filtering and pagination SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Search filtering and pagination workflow and verify queries return deterministic ordered results and preserved filter state.

### SRC-FD-STATEMENT-0081 — Search filtering and pagination: Failure handling

The Search filtering and pagination capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when unbounded scans and injection are prevented.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0093 — Search filtering and pagination: Idempotency and concurrency

Commands and operations for Search filtering and pagination SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0105 — Search filtering and pagination: Performance and resource bounds

The Search filtering and pagination implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-10 — Operations dashboard

A dashboard reports open work, overdue work, assignment load, completion lead time, and webhook
health from authoritative data.

Primary actor: **operations manager**. Successful outcome: **metrics reconcile to source records and expose freshness**. Principal deliverable: **dashboard queries, cards, and freshness indicators**.

### SRC-FD-STATEMENT-0010 — Operations dashboard: Core behavior

The FieldDesk implementation SHALL provide a dashboard reports open work, overdue work, assignment load, completion lead time, and webhook health from authoritative data.

Acceptance intent: Demonstrate that metrics reconcile to source records and expose freshness; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0022 — Operations dashboard: Input and state validation

The Operations dashboard capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, stale or partial data is labeled rather than presented as current.

### SRC-FD-STATEMENT-0034 — Operations dashboard: Interface contract

The public interfaces for Operations dashboard SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for dashboard queries, cards, and freshness indicators.

### SRC-FD-STATEMENT-0046 — Operations dashboard: Operator experience

The operator-facing workflow for Operations dashboard SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative operations manager can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0058 — Operations dashboard: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Operations dashboard SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0070 — Operations dashboard: Auditability and provenance

Every material transition and artifact produced by Operations dashboard SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Operations dashboard workflow and verify metrics reconcile to source records and expose freshness.

### SRC-FD-STATEMENT-0082 — Operations dashboard: Failure handling

The Operations dashboard capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when stale or partial data is labeled rather than presented as current.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0094 — Operations dashboard: Idempotency and concurrency

Commands and operations for Operations dashboard SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0106 — Operations dashboard: Performance and resource bounds

The Operations dashboard implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-11 — Outbound webhook integration

Signed idempotent webhooks notify a simulated partner about selected work-order events with retry,
dead-letter, and replay controls.

Primary actor: **integration operator**. Successful outcome: **each event is delivered at most once per idempotency key or safely retried**. Principal deliverable: **outbox, signer, delivery worker, and mock receiver**.

### SRC-FD-STATEMENT-0011 — Outbound webhook integration: Core behavior

The FieldDesk implementation SHALL provide signed idempotent webhooks notify a simulated partner about selected work-order events with retry, dead-letter, and replay controls.

Acceptance intent: Demonstrate that each event is delivered at most once per idempotency key or safely retried; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0023 — Outbound webhook integration: Input and state validation

The Outbound webhook integration capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, provider outage does not corrupt the work order transaction.

### SRC-FD-STATEMENT-0035 — Outbound webhook integration: Interface contract

The public interfaces for Outbound webhook integration SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for outbox, signer, delivery worker, and mock receiver.

### SRC-FD-STATEMENT-0047 — Outbound webhook integration: Operator experience

The operator-facing workflow for Outbound webhook integration SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative integration operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0059 — Outbound webhook integration: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Outbound webhook integration SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0071 — Outbound webhook integration: Auditability and provenance

Every material transition and artifact produced by Outbound webhook integration SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Outbound webhook integration workflow and verify each event is delivered at most once per idempotency key or safely retried.

### SRC-FD-STATEMENT-0083 — Outbound webhook integration: Failure handling

The Outbound webhook integration capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when provider outage does not corrupt the work order transaction.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0095 — Outbound webhook integration: Idempotency and concurrency

Commands and operations for Outbound webhook integration SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0107 — Outbound webhook integration: Performance and resource bounds

The Outbound webhook integration implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

## SRC-FD-FEATURE-12 — Database migrations and runtime

PostgreSQL migrations, Dockerized local services, health checks, backups, and environment validation
produce a reproducible development and release runtime.

Primary actor: **developer**. Successful outcome: **a clean environment can migrate forward and start all services**. Principal deliverable: **migrations, containers, health endpoints, and runbook**.

### SRC-FD-STATEMENT-0012 — Database migrations and runtime: Core behavior

The FieldDesk implementation SHALL provide postgreSQL migrations, Dockerized local services, health checks, backups, and environment validation produce a reproducible development and release runtime.

Acceptance intent: Demonstrate that a clean environment can migrate forward and start all services; all mandatory paths are covered by executable evidence.

### SRC-FD-STATEMENT-0024 — Database migrations and runtime: Input and state validation

The Database migrations and runtime capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, failed migrations are detected and recoverable.

### SRC-FD-STATEMENT-0036 — Database migrations and runtime: Interface contract

The public interfaces for Database migrations and runtime SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for migrations, containers, health endpoints, and runbook.

### SRC-FD-STATEMENT-0048 — Database migrations and runtime: Operator experience

The operator-facing workflow for Database migrations and runtime SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative developer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-FD-STATEMENT-0060 — Database migrations and runtime: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Database migrations and runtime SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-FD-STATEMENT-0072 — Database migrations and runtime: Auditability and provenance

Every material transition and artifact produced by Database migrations and runtime SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Database migrations and runtime workflow and verify a clean environment can migrate forward and start all services.

### SRC-FD-STATEMENT-0084 — Database migrations and runtime: Failure handling

The Database migrations and runtime capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when failed migrations are detected and recoverable.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-FD-STATEMENT-0096 — Database migrations and runtime: Idempotency and concurrency

Commands and operations for Database migrations and runtime SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-FD-STATEMENT-0108 — Database migrations and runtime: Performance and resource bounds

The Database migrations and runtime implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.
