# DemandForge — Source Requirement Statements

The statements below are authoritative visible source material. ProjectPipeline must normalize and trace them into its own requirement and work registries.

## SRC-DF-FEATURE-01 — Dataset ingestion

Batch ingestion accepts frozen CSV datasets for entities, dates, demand, price, promotion, weather,
and calendar context.

Primary actor: **data engineer**. Successful outcome: **valid batches are registered once with immutable fingerprints**. Principal deliverable: **ingestion pipeline and dataset manifest**.

### SRC-DF-STATEMENT-0001 — Dataset ingestion: Core behavior

The DemandForge implementation SHALL provide batch ingestion accepts frozen CSV datasets for entities, dates, demand, price, promotion, weather, and calendar context.

Acceptance intent: Demonstrate that valid batches are registered once with immutable fingerprints; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0017 — Dataset ingestion: Input and state validation

The Dataset ingestion capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, duplicate or partially uploaded batches are quarantined.

### SRC-DF-STATEMENT-0033 — Dataset ingestion: Interface contract

The public interfaces for Dataset ingestion SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for ingestion pipeline and dataset manifest.

### SRC-DF-STATEMENT-0049 — Dataset ingestion: Operator experience

The operator-facing workflow for Dataset ingestion SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative data engineer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0065 — Dataset ingestion: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Dataset ingestion SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0081 — Dataset ingestion: Auditability and provenance

Every material transition and artifact produced by Dataset ingestion SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Dataset ingestion workflow and verify valid batches are registered once with immutable fingerprints.

### SRC-DF-STATEMENT-0097 — Dataset ingestion: Failure handling

The Dataset ingestion capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when duplicate or partially uploaded batches are quarantined.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0113 — Dataset ingestion: Idempotency and concurrency

Commands and operations for Dataset ingestion SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0129 — Dataset ingestion: Performance and resource bounds

The Dataset ingestion implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0145 — Dataset ingestion: Verification and regression protection

The Dataset ingestion capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-02 — Schema and data quality

Typed contracts validate keys, ranges, missingness, duplicates, chronology, category drift, and
referential integrity.

Primary actor: **data steward**. Successful outcome: **quality findings are severity-ranked and block only according to policy**. Principal deliverable: **data quality engine and report**.

### SRC-DF-STATEMENT-0002 — Schema and data quality: Core behavior

The DemandForge implementation SHALL provide typed contracts validate keys, ranges, missingness, duplicates, chronology, category drift, and referential integrity.

Acceptance intent: Demonstrate that quality findings are severity-ranked and block only according to policy; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0018 — Schema and data quality: Input and state validation

The Schema and data quality capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, bad rows never silently enter training.

### SRC-DF-STATEMENT-0034 — Schema and data quality: Interface contract

The public interfaces for Schema and data quality SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for data quality engine and report.

### SRC-DF-STATEMENT-0050 — Schema and data quality: Operator experience

The operator-facing workflow for Schema and data quality SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative data steward can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0066 — Schema and data quality: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Schema and data quality SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0082 — Schema and data quality: Auditability and provenance

Every material transition and artifact produced by Schema and data quality SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Schema and data quality workflow and verify quality findings are severity-ranked and block only according to policy.

### SRC-DF-STATEMENT-0098 — Schema and data quality: Failure handling

The Schema and data quality capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when bad rows never silently enter training.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0114 — Schema and data quality: Idempotency and concurrency

Commands and operations for Schema and data quality SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0130 — Schema and data quality: Performance and resource bounds

The Schema and data quality implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0146 — Schema and data quality: Verification and regression protection

The Schema and data quality capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-03 — Point in time feature generation

Feature generation prevents future information leakage while producing lags, rolling statistics,
seasonality, promotions, and entity encodings.

Primary actor: **ML engineer**. Successful outcome: **every feature has an as-of timestamp and provenance**. Principal deliverable: **feature pipeline and registry**.

### SRC-DF-STATEMENT-0003 — Point in time feature generation: Core behavior

The DemandForge implementation SHALL provide feature generation prevents future information leakage while producing lags, rolling statistics, seasonality, promotions, and entity encodings.

Acceptance intent: Demonstrate that every feature has an as-of timestamp and provenance; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0019 — Point in time feature generation: Input and state validation

The Point in time feature generation capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, look-ahead leakage is detected by hidden adversarial tests.

### SRC-DF-STATEMENT-0035 — Point in time feature generation: Interface contract

The public interfaces for Point in time feature generation SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for feature pipeline and registry.

### SRC-DF-STATEMENT-0051 — Point in time feature generation: Operator experience

The operator-facing workflow for Point in time feature generation SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative ML engineer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0067 — Point in time feature generation: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Point in time feature generation SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0083 — Point in time feature generation: Auditability and provenance

Every material transition and artifact produced by Point in time feature generation SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Point in time feature generation workflow and verify every feature has an as-of timestamp and provenance.

### SRC-DF-STATEMENT-0099 — Point in time feature generation: Failure handling

The Point in time feature generation capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when look-ahead leakage is detected by hidden adversarial tests.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0115 — Point in time feature generation: Idempotency and concurrency

Commands and operations for Point in time feature generation SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0131 — Point in time feature generation: Performance and resource bounds

The Point in time feature generation implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0147 — Point in time feature generation: Verification and regression protection

The Point in time feature generation capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-04 — Temporal split strategy

Training, validation, calibration, and private holdout windows preserve chronology and entity
coverage.

Primary actor: **ML engineer**. Successful outcome: **splits are reproducible and leakage-free**. Principal deliverable: **split planner and manifests**.

### SRC-DF-STATEMENT-0004 — Temporal split strategy: Core behavior

The DemandForge implementation SHALL provide training, validation, calibration, and private holdout windows preserve chronology and entity coverage.

Acceptance intent: Demonstrate that splits are reproducible and leakage-free; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0020 — Temporal split strategy: Input and state validation

The Temporal split strategy capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, random row splitting is prohibited for time-series evaluation.

### SRC-DF-STATEMENT-0036 — Temporal split strategy: Interface contract

The public interfaces for Temporal split strategy SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for split planner and manifests.

### SRC-DF-STATEMENT-0052 — Temporal split strategy: Operator experience

The operator-facing workflow for Temporal split strategy SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative ML engineer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0068 — Temporal split strategy: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Temporal split strategy SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0084 — Temporal split strategy: Auditability and provenance

Every material transition and artifact produced by Temporal split strategy SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Temporal split strategy workflow and verify splits are reproducible and leakage-free.

### SRC-DF-STATEMENT-0100 — Temporal split strategy: Failure handling

The Temporal split strategy capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when random row splitting is prohibited for time-series evaluation.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0116 — Temporal split strategy: Idempotency and concurrency

Commands and operations for Temporal split strategy SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0132 — Temporal split strategy: Performance and resource bounds

The Temporal split strategy implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0148 — Temporal split strategy: Verification and regression protection

The Temporal split strategy capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-05 — Training orchestration

Training jobs use immutable configuration, dataset fingerprints, seeds, code version, leases,
checkpoints, and cancellation handling.

Primary actor: **ML operator**. Successful outcome: **an interrupted job can resume or fail cleanly without corrupt artifacts**. Principal deliverable: **training orchestrator and job store**.

### SRC-DF-STATEMENT-0005 — Training orchestration: Core behavior

The DemandForge implementation SHALL provide training jobs use immutable configuration, dataset fingerprints, seeds, code version, leases, checkpoints, and cancellation handling.

Acceptance intent: Demonstrate that an interrupted job can resume or fail cleanly without corrupt artifacts; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0021 — Training orchestration: Input and state validation

The Training orchestration capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, duplicate job submissions do not consume duplicate budget.

### SRC-DF-STATEMENT-0037 — Training orchestration: Interface contract

The public interfaces for Training orchestration SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for training orchestrator and job store.

### SRC-DF-STATEMENT-0053 — Training orchestration: Operator experience

The operator-facing workflow for Training orchestration SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative ML operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0069 — Training orchestration: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Training orchestration SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0085 — Training orchestration: Auditability and provenance

Every material transition and artifact produced by Training orchestration SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Training orchestration workflow and verify an interrupted job can resume or fail cleanly without corrupt artifacts.

### SRC-DF-STATEMENT-0101 — Training orchestration: Failure handling

The Training orchestration capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when duplicate job submissions do not consume duplicate budget.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0117 — Training orchestration: Idempotency and concurrency

Commands and operations for Training orchestration SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0133 — Training orchestration: Performance and resource bounds

The Training orchestration implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0149 — Training orchestration: Verification and regression protection

The Training orchestration capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-06 — Seasonal naive baseline

A transparent seasonal-naive model establishes a mandatory benchmark for every forecast horizon and
segment.

Primary actor: **analyst**. Successful outcome: **baseline metrics are always available and reproducible**. Principal deliverable: **baseline model implementation**.

### SRC-DF-STATEMENT-0006 — Seasonal naive baseline: Core behavior

The DemandForge implementation SHALL provide a transparent seasonal-naive model establishes a mandatory benchmark for every forecast horizon and segment.

Acceptance intent: Demonstrate that baseline metrics are always available and reproducible; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0022 — Seasonal naive baseline: Input and state validation

The Seasonal naive baseline capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, complex models cannot be promoted without beating the baseline policy.

### SRC-DF-STATEMENT-0038 — Seasonal naive baseline: Interface contract

The public interfaces for Seasonal naive baseline SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for baseline model implementation.

### SRC-DF-STATEMENT-0054 — Seasonal naive baseline: Operator experience

The operator-facing workflow for Seasonal naive baseline SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative analyst can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0070 — Seasonal naive baseline: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Seasonal naive baseline SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0086 — Seasonal naive baseline: Auditability and provenance

Every material transition and artifact produced by Seasonal naive baseline SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Seasonal naive baseline workflow and verify baseline metrics are always available and reproducible.

### SRC-DF-STATEMENT-0102 — Seasonal naive baseline: Failure handling

The Seasonal naive baseline capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when complex models cannot be promoted without beating the baseline policy.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0118 — Seasonal naive baseline: Idempotency and concurrency

Commands and operations for Seasonal naive baseline SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0134 — Seasonal naive baseline: Performance and resource bounds

The Seasonal naive baseline implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0150 — Seasonal naive baseline: Verification and regression protection

The Seasonal naive baseline capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-07 — Gradient boosted candidate

An optional CPU-friendly gradient-boosted candidate uses approved features and bounded
hyperparameter search.

Primary actor: **ML engineer**. Successful outcome: **the candidate trains within declared resource limits**. Principal deliverable: **candidate model adapter**.

### SRC-DF-STATEMENT-0007 — Gradient boosted candidate: Core behavior

The DemandForge implementation SHALL provide an optional CPU-friendly gradient-boosted candidate uses approved features and bounded hyperparameter search.

Acceptance intent: Demonstrate that the candidate trains within declared resource limits; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0023 — Gradient boosted candidate: Input and state validation

The Gradient boosted candidate capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, missing optional dependencies trigger a documented fallback.

### SRC-DF-STATEMENT-0039 — Gradient boosted candidate: Interface contract

The public interfaces for Gradient boosted candidate SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for candidate model adapter.

### SRC-DF-STATEMENT-0055 — Gradient boosted candidate: Operator experience

The operator-facing workflow for Gradient boosted candidate SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative ML engineer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0071 — Gradient boosted candidate: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Gradient boosted candidate SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0087 — Gradient boosted candidate: Auditability and provenance

Every material transition and artifact produced by Gradient boosted candidate SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Gradient boosted candidate workflow and verify the candidate trains within declared resource limits.

### SRC-DF-STATEMENT-0103 — Gradient boosted candidate: Failure handling

The Gradient boosted candidate capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when missing optional dependencies trigger a documented fallback.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0119 — Gradient boosted candidate: Idempotency and concurrency

Commands and operations for Gradient boosted candidate SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0135 — Gradient boosted candidate: Performance and resource bounds

The Gradient boosted candidate implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0151 — Gradient boosted candidate: Verification and regression protection

The Gradient boosted candidate capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-08 — Evaluation and calibration

Evaluation calculates MAE, WAPE, bias, interval coverage, segment breakdowns, and stability across
forecast horizons.

Primary actor: **model reviewer**. Successful outcome: **metrics are computed from the frozen holdout and retain uncertainty**. Principal deliverable: **evaluation and calibration package**.

### SRC-DF-STATEMENT-0008 — Evaluation and calibration: Core behavior

The DemandForge implementation SHALL provide evaluation calculates MAE, WAPE, bias, interval coverage, segment breakdowns, and stability across forecast horizons.

Acceptance intent: Demonstrate that metrics are computed from the frozen holdout and retain uncertainty; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0024 — Evaluation and calibration: Input and state validation

The Evaluation and calibration capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, aggregate improvements cannot hide severe segment regressions.

### SRC-DF-STATEMENT-0040 — Evaluation and calibration: Interface contract

The public interfaces for Evaluation and calibration SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for evaluation and calibration package.

### SRC-DF-STATEMENT-0056 — Evaluation and calibration: Operator experience

The operator-facing workflow for Evaluation and calibration SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative model reviewer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0072 — Evaluation and calibration: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Evaluation and calibration SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0088 — Evaluation and calibration: Auditability and provenance

Every material transition and artifact produced by Evaluation and calibration SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Evaluation and calibration workflow and verify metrics are computed from the frozen holdout and retain uncertainty.

### SRC-DF-STATEMENT-0104 — Evaluation and calibration: Failure handling

The Evaluation and calibration capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when aggregate improvements cannot hide severe segment regressions.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0120 — Evaluation and calibration: Idempotency and concurrency

Commands and operations for Evaluation and calibration SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0136 — Evaluation and calibration: Performance and resource bounds

The Evaluation and calibration implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0152 — Evaluation and calibration: Verification and regression protection

The Evaluation and calibration capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-09 — Champion challenger registry

Model versions, metrics, artifacts, approvals, and rollback lineage are stored in a local registry
with champion/challenger decisions.

Primary actor: **model owner**. Successful outcome: **only a qualified model can become champion**. Principal deliverable: **model registry and promotion gate**.

### SRC-DF-STATEMENT-0009 — Champion challenger registry: Core behavior

The DemandForge implementation SHALL provide model versions, metrics, artifacts, approvals, and rollback lineage are stored in a local registry with champion/challenger decisions.

Acceptance intent: Demonstrate that only a qualified model can become champion; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0025 — Champion challenger registry: Input and state validation

The Champion challenger registry capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, artifact mismatch or missing evidence blocks promotion.

### SRC-DF-STATEMENT-0041 — Champion challenger registry: Interface contract

The public interfaces for Champion challenger registry SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for model registry and promotion gate.

### SRC-DF-STATEMENT-0057 — Champion challenger registry: Operator experience

The operator-facing workflow for Champion challenger registry SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative model owner can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0073 — Champion challenger registry: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Champion challenger registry SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0089 — Champion challenger registry: Auditability and provenance

Every material transition and artifact produced by Champion challenger registry SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Champion challenger registry workflow and verify only a qualified model can become champion.

### SRC-DF-STATEMENT-0105 — Champion challenger registry: Failure handling

The Champion challenger registry capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when artifact mismatch or missing evidence blocks promotion.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0121 — Champion challenger registry: Idempotency and concurrency

Commands and operations for Champion challenger registry SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0137 — Champion challenger registry: Performance and resource bounds

The Champion challenger registry implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0153 — Champion challenger registry: Verification and regression protection

The Champion challenger registry capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-10 — Batch forecasting

Scheduled batch forecasts produce entity-date-horizon predictions, uncertainty bands, model
identifiers, and data freshness metadata.

Primary actor: **planner**. Successful outcome: **reruns with identical inputs are idempotent**. Principal deliverable: **batch forecast job and artifact schema**.

### SRC-DF-STATEMENT-0010 — Batch forecasting: Core behavior

The DemandForge implementation SHALL provide scheduled batch forecasts produce entity-date-horizon predictions, uncertainty bands, model identifiers, and data freshness metadata.

Acceptance intent: Demonstrate that reruns with identical inputs are idempotent; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0026 — Batch forecasting: Input and state validation

The Batch forecasting capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, partial output is never published as complete.

### SRC-DF-STATEMENT-0042 — Batch forecasting: Interface contract

The public interfaces for Batch forecasting SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for batch forecast job and artifact schema.

### SRC-DF-STATEMENT-0058 — Batch forecasting: Operator experience

The operator-facing workflow for Batch forecasting SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative planner can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0074 — Batch forecasting: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Batch forecasting SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0090 — Batch forecasting: Auditability and provenance

Every material transition and artifact produced by Batch forecasting SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Batch forecasting workflow and verify reruns with identical inputs are idempotent.

### SRC-DF-STATEMENT-0106 — Batch forecasting: Failure handling

The Batch forecasting capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when partial output is never published as complete.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0122 — Batch forecasting: Idempotency and concurrency

Commands and operations for Batch forecasting SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0138 — Batch forecasting: Performance and resource bounds

The Batch forecasting implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0154 — Batch forecasting: Verification and regression protection

The Batch forecasting capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-11 — Inference API

A versioned API serves bounded forecast requests with model metadata, uncertainty, health, and clear
unavailable states.

Primary actor: **application client**. Successful outcome: **valid requests return stable schemas within latency limits**. Principal deliverable: **inference service and OpenAPI contract**.

### SRC-DF-STATEMENT-0011 — Inference API: Core behavior

The DemandForge implementation SHALL provide a versioned API serves bounded forecast requests with model metadata, uncertainty, health, and clear unavailable states.

Acceptance intent: Demonstrate that valid requests return stable schemas within latency limits; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0027 — Inference API: Input and state validation

The Inference API capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unknown entities and unavailable models fail explicitly.

### SRC-DF-STATEMENT-0043 — Inference API: Interface contract

The public interfaces for Inference API SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for inference service and OpenAPI contract.

### SRC-DF-STATEMENT-0059 — Inference API: Operator experience

The operator-facing workflow for Inference API SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative application client can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0075 — Inference API: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Inference API SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0091 — Inference API: Auditability and provenance

Every material transition and artifact produced by Inference API SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Inference API workflow and verify valid requests return stable schemas within latency limits.

### SRC-DF-STATEMENT-0107 — Inference API: Failure handling

The Inference API capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when unknown entities and unavailable models fail explicitly.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0123 — Inference API: Idempotency and concurrency

Commands and operations for Inference API SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0139 — Inference API: Performance and resource bounds

The Inference API implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0155 — Inference API: Verification and regression protection

The Inference API capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-12 — Uncertainty and fallback

Prediction intervals, sparse-history handling, cold-start priors, and model fallback rules
communicate uncertainty honestly.

Primary actor: **planner**. Successful outcome: **low-confidence forecasts are labeled and traceable**. Principal deliverable: **uncertainty policy and fallback engine**.

### SRC-DF-STATEMENT-0012 — Uncertainty and fallback: Core behavior

The DemandForge implementation SHALL provide prediction intervals, sparse-history handling, cold-start priors, and model fallback rules communicate uncertainty honestly.

Acceptance intent: Demonstrate that low-confidence forecasts are labeled and traceable; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0028 — Uncertainty and fallback: Input and state validation

The Uncertainty and fallback capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, the service never fabricates precision for unsupported cases.

### SRC-DF-STATEMENT-0044 — Uncertainty and fallback: Interface contract

The public interfaces for Uncertainty and fallback SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for uncertainty policy and fallback engine.

### SRC-DF-STATEMENT-0060 — Uncertainty and fallback: Operator experience

The operator-facing workflow for Uncertainty and fallback SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative planner can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0076 — Uncertainty and fallback: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Uncertainty and fallback SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0092 — Uncertainty and fallback: Auditability and provenance

Every material transition and artifact produced by Uncertainty and fallback SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Uncertainty and fallback workflow and verify low-confidence forecasts are labeled and traceable.

### SRC-DF-STATEMENT-0108 — Uncertainty and fallback: Failure handling

The Uncertainty and fallback capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when the service never fabricates precision for unsupported cases.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0124 — Uncertainty and fallback: Idempotency and concurrency

Commands and operations for Uncertainty and fallback SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0140 — Uncertainty and fallback: Performance and resource bounds

The Uncertainty and fallback implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0156 — Uncertainty and fallback: Verification and regression protection

The Uncertainty and fallback capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-13 — Drift and data quality monitoring

Monitoring detects input drift, missing feeds, forecast bias, interval coverage decay, and stale
champions.

Primary actor: **ML operator**. Successful outcome: **alerts include scope, evidence, severity, and recommended action**. Principal deliverable: **monitoring jobs and dashboards**.

### SRC-DF-STATEMENT-0013 — Drift and data quality monitoring: Core behavior

The DemandForge implementation SHALL provide monitoring detects input drift, missing feeds, forecast bias, interval coverage decay, and stale champions.

Acceptance intent: Demonstrate that alerts include scope, evidence, severity, and recommended action; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0029 — Drift and data quality monitoring: Input and state validation

The Drift and data quality monitoring capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, monitoring does not retrain or promote automatically outside policy.

### SRC-DF-STATEMENT-0045 — Drift and data quality monitoring: Interface contract

The public interfaces for Drift and data quality monitoring SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for monitoring jobs and dashboards.

### SRC-DF-STATEMENT-0061 — Drift and data quality monitoring: Operator experience

The operator-facing workflow for Drift and data quality monitoring SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative ML operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0077 — Drift and data quality monitoring: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Drift and data quality monitoring SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0093 — Drift and data quality monitoring: Auditability and provenance

Every material transition and artifact produced by Drift and data quality monitoring SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Drift and data quality monitoring workflow and verify alerts include scope, evidence, severity, and recommended action.

### SRC-DF-STATEMENT-0109 — Drift and data quality monitoring: Failure handling

The Drift and data quality monitoring capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when monitoring does not retrain or promote automatically outside policy.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0125 — Drift and data quality monitoring: Idempotency and concurrency

Commands and operations for Drift and data quality monitoring SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0141 — Drift and data quality monitoring: Performance and resource bounds

The Drift and data quality monitoring implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0157 — Drift and data quality monitoring: Verification and regression protection

The Drift and data quality monitoring capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-14 — Experiment reproducibility

Every experiment can be reconstructed from code version, environment lock, data hashes, parameters,
random seeds, and captured outputs.

Primary actor: **reviewer**. Successful outcome: **independent reruns reproduce metrics within tolerance**. Principal deliverable: **experiment record and replay command**.

### SRC-DF-STATEMENT-0014 — Experiment reproducibility: Core behavior

The DemandForge implementation SHALL provide every experiment can be reconstructed from code version, environment lock, data hashes, parameters, random seeds, and captured outputs.

Acceptance intent: Demonstrate that independent reruns reproduce metrics within tolerance; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0030 — Experiment reproducibility: Input and state validation

The Experiment reproducibility capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, untracked notebook state is not accepted as evidence.

### SRC-DF-STATEMENT-0046 — Experiment reproducibility: Interface contract

The public interfaces for Experiment reproducibility SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for experiment record and replay command.

### SRC-DF-STATEMENT-0062 — Experiment reproducibility: Operator experience

The operator-facing workflow for Experiment reproducibility SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative reviewer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0078 — Experiment reproducibility: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Experiment reproducibility SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0094 — Experiment reproducibility: Auditability and provenance

Every material transition and artifact produced by Experiment reproducibility SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Experiment reproducibility workflow and verify independent reruns reproduce metrics within tolerance.

### SRC-DF-STATEMENT-0110 — Experiment reproducibility: Failure handling

The Experiment reproducibility capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when untracked notebook state is not accepted as evidence.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0126 — Experiment reproducibility: Idempotency and concurrency

Commands and operations for Experiment reproducibility SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0142 — Experiment reproducibility: Performance and resource bounds

The Experiment reproducibility implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0158 — Experiment reproducibility: Verification and regression protection

The Experiment reproducibility capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-15 — Resource admission and scheduling

CPU, memory, GPU, disk, and concurrency leases are evaluated before expensive work and released
after completion or crash recovery.

Primary actor: **scheduler**. Successful outcome: **jobs wait, degrade, or fall back according to policy**. Principal deliverable: **resource governor and lease ledger**.

### SRC-DF-STATEMENT-0015 — Resource admission and scheduling: Core behavior

The DemandForge implementation SHALL provide cPU, memory, GPU, disk, and concurrency leases are evaluated before expensive work and released after completion or crash recovery.

Acceptance intent: Demonstrate that jobs wait, degrade, or fall back according to policy; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0031 — Resource admission and scheduling: Input and state validation

The Resource admission and scheduling capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, resource scarcity never causes uncontrolled oversubscription.

### SRC-DF-STATEMENT-0047 — Resource admission and scheduling: Interface contract

The public interfaces for Resource admission and scheduling SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for resource governor and lease ledger.

### SRC-DF-STATEMENT-0063 — Resource admission and scheduling: Operator experience

The operator-facing workflow for Resource admission and scheduling SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative scheduler can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0079 — Resource admission and scheduling: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Resource admission and scheduling SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0095 — Resource admission and scheduling: Auditability and provenance

Every material transition and artifact produced by Resource admission and scheduling SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Resource admission and scheduling workflow and verify jobs wait, degrade, or fall back according to policy.

### SRC-DF-STATEMENT-0111 — Resource admission and scheduling: Failure handling

The Resource admission and scheduling capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when resource scarcity never causes uncontrolled oversubscription.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0127 — Resource admission and scheduling: Idempotency and concurrency

Commands and operations for Resource admission and scheduling SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0143 — Resource admission and scheduling: Performance and resource bounds

The Resource admission and scheduling implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0159 — Resource admission and scheduling: Verification and regression protection

The Resource admission and scheduling capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.

## SRC-DF-FEATURE-16 — Budget governance reporting and handoff

Per-job cost estimates, caps, provider quotas, final model card, runbooks, and release artifacts
support safe operation and audit.

Primary actor: **program owner**. Successful outcome: **budget breaches block admission and all outcomes are explainable**. Principal deliverable: **budget governor, reports, model card, and runbook**.

### SRC-DF-STATEMENT-0016 — Budget governance reporting and handoff: Core behavior

The DemandForge implementation SHALL provide per-job cost estimates, caps, provider quotas, final model card, runbooks, and release artifacts support safe operation and audit.

Acceptance intent: Demonstrate that budget breaches block admission and all outcomes are explainable; all mandatory paths are covered by executable evidence.

### SRC-DF-STATEMENT-0032 — Budget governance reporting and handoff: Input and state validation

The Budget governance reporting and handoff capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, cost uncertainty is labeled rather than ignored.

### SRC-DF-STATEMENT-0048 — Budget governance reporting and handoff: Interface contract

The public interfaces for Budget governance reporting and handoff SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for budget governor, reports, model card, and runbook.

### SRC-DF-STATEMENT-0064 — Budget governance reporting and handoff: Operator experience

The operator-facing workflow for Budget governance reporting and handoff SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative program owner can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-DF-STATEMENT-0080 — Budget governance reporting and handoff: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Budget governance reporting and handoff SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

### SRC-DF-STATEMENT-0096 — Budget governance reporting and handoff: Auditability and provenance

Every material transition and artifact produced by Budget governance reporting and handoff SHALL record actor, correlation identifier, source/input identity, prior state, resulting state, timestamp, and evidence linkage.

Acceptance intent: The audit trail can reconstruct the complete Budget governance reporting and handoff workflow and verify budget breaches block admission and all outcomes are explainable.

### SRC-DF-STATEMENT-0112 — Budget governance reporting and handoff: Failure handling

The Budget governance reporting and handoff capability SHALL fail closed or degrade according to policy, preserve recoverable work, and expose a bounded actionable error when cost uncertainty is labeled rather than ignored.

Acceptance intent: Injected failures do not create false success, corrupt authoritative state, leak secrets, or prevent unrelated safe work from continuing.

### SRC-DF-STATEMENT-0128 — Budget governance reporting and handoff: Idempotency and concurrency

Commands and operations for Budget governance reporting and handoff SHALL use idempotency keys, version checks, leases, ownership, or equivalent controls so retries and concurrent attempts cannot create conflicting side effects.

Acceptance intent: Repeated and overlapping requests converge to one valid result while conflicts are surfaced for deliberate resolution.

### SRC-DF-STATEMENT-0144 — Budget governance reporting and handoff: Performance and resource bounds

The Budget governance reporting and handoff implementation SHALL declare and enforce relevant latency, throughput, memory, storage, file-size, concurrency, and timeout bounds for the benchmark environment.

Acceptance intent: Representative workloads complete within the frozen thresholds and excessive workloads are rejected or queued predictably.

### SRC-DF-STATEMENT-0160 — Budget governance reporting and handoff: Verification and regression protection

The Budget governance reporting and handoff capability SHALL be covered by deterministic unit, contract, integration, and end-to-end tests appropriate to its boundaries, including at least one negative regression case.

Acceptance intent: The relevant tests fail against a known defective mutant and pass against the qualified reference implementation.
