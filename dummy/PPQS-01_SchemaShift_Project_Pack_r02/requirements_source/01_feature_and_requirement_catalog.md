# SchemaShift — Source Requirement Statements

The statements below are authoritative visible source material. ProjectPipeline must normalize and trace them into its own requirement and work registries.

## SRC-SS-FEATURE-01 — Schema registry

A versioned registry defines supported schema versions, canonical identifiers, compatibility
metadata, and migration adjacency.

Primary actor: **library consumer**. Successful outcome: **supported schemas are discoverable and immutable once published**. Principal deliverable: **schema registry module and machine-readable catalog**.

### SRC-SS-STATEMENT-0001 — Schema registry: Core behavior

The SchemaShift implementation SHALL provide a versioned registry defines supported schema versions, canonical identifiers, compatibility metadata, and migration adjacency.

Acceptance intent: Demonstrate that supported schemas are discoverable and immutable once published; all mandatory paths are covered by executable evidence.

### SRC-SS-STATEMENT-0009 — Schema registry: Input and state validation

The Schema registry capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unknown or duplicated schema identifiers are rejected.

### SRC-SS-STATEMENT-0017 — Schema registry: Interface contract

The public interfaces for Schema registry SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for schema registry module and machine-readable catalog.

### SRC-SS-STATEMENT-0025 — Schema registry: Operator experience

The operator-facing workflow for Schema registry SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative library consumer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-SS-STATEMENT-0033 — Schema registry: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Schema registry SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

## SRC-SS-FEATURE-02 — Version one to version two migration

Deterministic transforms migrate legacy service, logging, and retry settings from schema v1 into
schema v2.

Primary actor: **CLI operator**. Successful outcome: **valid v1 inputs become semantically equivalent v2 documents**. Principal deliverable: **v1_to_v2 migration implementation**.

### SRC-SS-STATEMENT-0002 — Version one to version two migration: Core behavior

The SchemaShift implementation SHALL provide deterministic transforms migrate legacy service, logging, and retry settings from schema v1 into schema v2.

Acceptance intent: Demonstrate that valid v1 inputs become semantically equivalent v2 documents; all mandatory paths are covered by executable evidence.

### SRC-SS-STATEMENT-0010 — Version one to version two migration: Input and state validation

The Version one to version two migration capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, invalid or ambiguous legacy values fail without changing the source.

### SRC-SS-STATEMENT-0018 — Version one to version two migration: Interface contract

The public interfaces for Version one to version two migration SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for v1_to_v2 migration implementation.

### SRC-SS-STATEMENT-0026 — Version one to version two migration: Operator experience

The operator-facing workflow for Version one to version two migration SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative CLI operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-SS-STATEMENT-0034 — Version one to version two migration: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Version one to version two migration SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

## SRC-SS-FEATURE-03 — Version two to version three migration

Deterministic transforms migrate v2 secrets references, execution policy, and observability settings
into schema v3.

Primary actor: **CLI operator**. Successful outcome: **valid v2 inputs become canonical v3 documents**. Principal deliverable: **v2_to_v3 migration implementation**.

### SRC-SS-STATEMENT-0003 — Version two to version three migration: Core behavior

The SchemaShift implementation SHALL provide deterministic transforms migrate v2 secrets references, execution policy, and observability settings into schema v3.

Acceptance intent: Demonstrate that valid v2 inputs become canonical v3 documents; all mandatory paths are covered by executable evidence.

### SRC-SS-STATEMENT-0011 — Version two to version three migration: Input and state validation

The Version two to version three migration capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unsupported downgrade-only constructs are reported clearly.

### SRC-SS-STATEMENT-0019 — Version two to version three migration: Interface contract

The public interfaces for Version two to version three migration SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for v2_to_v3 migration implementation.

### SRC-SS-STATEMENT-0027 — Version two to version three migration: Operator experience

The operator-facing workflow for Version two to version three migration SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative CLI operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-SS-STATEMENT-0035 — Version two to version three migration: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Version two to version three migration SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

## SRC-SS-FEATURE-04 — Validation diagnostics

Strict structural and semantic validation returns stable machine-readable codes, paths, severity,
and corrective guidance.

Primary actor: **developer**. Successful outcome: **all invalid fixtures receive precise diagnostics**. Principal deliverable: **validator and diagnostic schema**.

### SRC-SS-STATEMENT-0004 — Validation diagnostics: Core behavior

The SchemaShift implementation SHALL provide strict structural and semantic validation returns stable machine-readable codes, paths, severity, and corrective guidance.

Acceptance intent: Demonstrate that all invalid fixtures receive precise diagnostics; all mandatory paths are covered by executable evidence.

### SRC-SS-STATEMENT-0012 — Validation diagnostics: Input and state validation

The Validation diagnostics capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, validation never crashes or silently coerces unsafe values.

### SRC-SS-STATEMENT-0020 — Validation diagnostics: Interface contract

The public interfaces for Validation diagnostics SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for validator and diagnostic schema.

### SRC-SS-STATEMENT-0028 — Validation diagnostics: Operator experience

The operator-facing workflow for Validation diagnostics SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative developer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-SS-STATEMENT-0036 — Validation diagnostics: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Validation diagnostics SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

## SRC-SS-FEATURE-05 — Migration planning

A planner calculates the safe ordered path between supported versions and explains every transform
before execution.

Primary actor: **release engineer**. Successful outcome: **the plan is complete, minimal, and deterministic**. Principal deliverable: **migration plan model and CLI command**.

### SRC-SS-STATEMENT-0005 — Migration planning: Core behavior

The SchemaShift implementation SHALL provide a planner calculates the safe ordered path between supported versions and explains every transform before execution.

Acceptance intent: Demonstrate that the plan is complete, minimal, and deterministic; all mandatory paths are covered by executable evidence.

### SRC-SS-STATEMENT-0013 — Migration planning: Input and state validation

The Migration planning capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, missing path or cycle conditions are blocked.

### SRC-SS-STATEMENT-0021 — Migration planning: Interface contract

The public interfaces for Migration planning SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for migration plan model and CLI command.

### SRC-SS-STATEMENT-0029 — Migration planning: Operator experience

The operator-facing workflow for Migration planning SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative release engineer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-SS-STATEMENT-0037 — Migration planning: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Migration planning SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

## SRC-SS-FEATURE-06 — Dry-run semantic diff

Dry-run mode reports normalized semantic changes without mutating the source or writing backups.

Primary actor: **reviewer**. Successful outcome: **the diff distinguishes added, removed, moved, and transformed values**. Principal deliverable: **semantic diff engine and report**.

### SRC-SS-STATEMENT-0006 — Dry-run semantic diff: Core behavior

The SchemaShift implementation SHALL provide dry-run mode reports normalized semantic changes without mutating the source or writing backups.

Acceptance intent: Demonstrate that the diff distinguishes added, removed, moved, and transformed values; all mandatory paths are covered by executable evidence.

### SRC-SS-STATEMENT-0014 — Dry-run semantic diff: Input and state validation

The Dry-run semantic diff capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, sensitive values are never echoed.

### SRC-SS-STATEMENT-0022 — Dry-run semantic diff: Interface contract

The public interfaces for Dry-run semantic diff SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for semantic diff engine and report.

### SRC-SS-STATEMENT-0030 — Dry-run semantic diff: Operator experience

The operator-facing workflow for Dry-run semantic diff SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative reviewer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-SS-STATEMENT-0038 — Dry-run semantic diff: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Dry-run semantic diff SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

## SRC-SS-FEATURE-07 — Backup and rollback

Committed migrations use atomic writes, content-addressed backups, rollback eligibility checks, and
corruption detection.

Primary actor: **operator**. Successful outcome: **a failed write restores the original and a permitted rollback is verifiable**. Principal deliverable: **transaction and rollback subsystem**.

### SRC-SS-STATEMENT-0007 — Backup and rollback: Core behavior

The SchemaShift implementation SHALL provide committed migrations use atomic writes, content-addressed backups, rollback eligibility checks, and corruption detection.

Acceptance intent: Demonstrate that a failed write restores the original and a permitted rollback is verifiable; all mandatory paths are covered by executable evidence.

### SRC-SS-STATEMENT-0015 — Backup and rollback: Input and state validation

The Backup and rollback capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, partial or mismatched backups are quarantined.

### SRC-SS-STATEMENT-0023 — Backup and rollback: Interface contract

The public interfaces for Backup and rollback SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for transaction and rollback subsystem.

### SRC-SS-STATEMENT-0031 — Backup and rollback: Operator experience

The operator-facing workflow for Backup and rollback SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-SS-STATEMENT-0039 — Backup and rollback: Authorization and least privilege

All reads, mutations, exports, and external effects associated with Backup and rollback SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.

## SRC-SS-FEATURE-08 — CLI SDK documentation and release

A typed Python API and command-line interface expose validate, plan, migrate, diff, rollback, and
inspect operations with complete handoff documentation.

Primary actor: **integrator**. Successful outcome: **the package installs, commands are discoverable, and examples are executable**. Principal deliverable: **Python package, CLI, examples, release notes, and runbook**.

### SRC-SS-STATEMENT-0008 — CLI SDK documentation and release: Core behavior

The SchemaShift implementation SHALL provide a typed Python API and command-line interface expose validate, plan, migrate, diff, rollback, and inspect operations with complete handoff documentation.

Acceptance intent: Demonstrate that the package installs, commands are discoverable, and examples are executable; all mandatory paths are covered by executable evidence.

### SRC-SS-STATEMENT-0016 — CLI SDK documentation and release: Input and state validation

The CLI SDK documentation and release capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unsupported usage returns stable nonzero exit codes.

### SRC-SS-STATEMENT-0024 — CLI SDK documentation and release: Interface contract

The public interfaces for CLI SDK documentation and release SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for Python package, CLI, examples, release notes, and runbook.

### SRC-SS-STATEMENT-0032 — CLI SDK documentation and release: Operator experience

The operator-facing workflow for CLI SDK documentation and release SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative integrator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

### SRC-SS-STATEMENT-0040 — CLI SDK documentation and release: Authorization and least privilege

All reads, mutations, exports, and external effects associated with CLI SDK documentation and release SHALL enforce least privilege and deny unauthorized access at the authoritative service boundary.

Acceptance intent: Authorized roles succeed and unauthorized, cross-scope, or unauthenticated attempts fail without revealing protected data.
