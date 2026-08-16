# Repository Safety Patch — Source Requirement Statements

The statements below are authoritative visible source material. ProjectPipeline must normalize and trace them into its own requirement and work registries.

## SRC-RP-FEATURE-01 — Truncated key metadata

Repository key metadata shorter than encryption overhead must return a stable error instead of
slicing beyond bounds.

Primary actor: **repository operator**. Successful outcome: **every undersized key payload is rejected cleanly**. Principal deliverable: **key loading guard**.

### SRC-RP-STATEMENT-0001 — Truncated key metadata: Core behavior

The Historical Patch Replay implementation SHALL provide repository key metadata shorter than encryption overhead must return a stable error instead of slicing beyond bounds.

Acceptance intent: Demonstrate that every undersized key payload is rejected cleanly; all mandatory paths are covered by executable evidence.

### SRC-RP-STATEMENT-0007 — Truncated key metadata: Input and state validation

The Truncated key metadata capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, no command panics while searching keys.

### SRC-RP-STATEMENT-0013 — Truncated key metadata: Interface contract

The public interfaces for Truncated key metadata SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for key loading guard.

### SRC-RP-STATEMENT-0019 — Truncated key metadata: Operator experience

The operator-facing workflow for Truncated key metadata SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative repository operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

## SRC-RP-FEATURE-02 — Truncated configuration metadata

Configuration metadata shorter than encryption overhead must return a stable typed error before
decryption.

Primary actor: **repository operator**. Successful outcome: **undersized configuration payloads fail cleanly**. Principal deliverable: **configuration loading guard**.

### SRC-RP-STATEMENT-0002 — Truncated configuration metadata: Core behavior

The Historical Patch Replay implementation SHALL provide configuration metadata shorter than encryption overhead must return a stable typed error before decryption.

Acceptance intent: Demonstrate that undersized configuration payloads fail cleanly; all mandatory paths are covered by executable evidence.

### SRC-RP-STATEMENT-0008 — Truncated configuration metadata: Input and state validation

The Truncated configuration metadata capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, config loading never reaches an unsafe slice.

### SRC-RP-STATEMENT-0014 — Truncated configuration metadata: Interface contract

The public interfaces for Truncated configuration metadata SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for configuration loading guard.

### SRC-RP-STATEMENT-0020 — Truncated configuration metadata: Operator experience

The operator-facing workflow for Truncated configuration metadata SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative repository operator can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

## SRC-RP-FEATURE-03 — Error compatibility

New diagnostics remain actionable without changing cryptographic verification, authentication, or
valid repository behavior.

Primary actor: **CLI user**. Successful outcome: **valid repositories behave identically and corrupt ones receive clear errors**. Principal deliverable: **error semantics and compatibility notes**.

### SRC-RP-STATEMENT-0003 — Error compatibility: Core behavior

The Historical Patch Replay implementation SHALL provide new diagnostics remain actionable without changing cryptographic verification, authentication, or valid repository behavior.

Acceptance intent: Demonstrate that valid repositories behave identically and corrupt ones receive clear errors; all mandatory paths are covered by executable evidence.

### SRC-RP-STATEMENT-0009 — Error compatibility: Input and state validation

The Error compatibility capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, the patch does not broaden trust or weaken MAC checks.

### SRC-RP-STATEMENT-0015 — Error compatibility: Interface contract

The public interfaces for Error compatibility SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for error semantics and compatibility notes.

### SRC-RP-STATEMENT-0021 — Error compatibility: Operator experience

The operator-facing workflow for Error compatibility SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative CLI user can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

## SRC-RP-FEATURE-04 — Focused regression tests

Table-driven tests cover nil, empty, one-byte, and just-below-minimum data for both affected paths.

Primary actor: **maintainer**. Successful outcome: **tests fail on the baseline and pass on the repaired implementation**. Principal deliverable: **Go regression tests**.

### SRC-RP-STATEMENT-0004 — Focused regression tests: Core behavior

The Historical Patch Replay implementation SHALL provide table-driven tests cover nil, empty, one-byte, and just-below-minimum data for both affected paths.

Acceptance intent: Demonstrate that tests fail on the baseline and pass on the repaired implementation; all mandatory paths are covered by executable evidence.

### SRC-RP-STATEMENT-0010 — Focused regression tests: Input and state validation

The Focused regression tests capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, tests do not require network or external repositories.

### SRC-RP-STATEMENT-0016 — Focused regression tests: Interface contract

The public interfaces for Focused regression tests SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for Go regression tests.

### SRC-RP-STATEMENT-0022 — Focused regression tests: Operator experience

The operator-facing workflow for Focused regression tests SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative maintainer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

## SRC-RP-FEATURE-05 — Build format and scope discipline

The change remains minimal, formatted, buildable, and isolated to the unsafe read paths and their
tests.

Primary actor: **maintainer**. Successful outcome: **repository formatting and relevant packages pass**. Principal deliverable: **small patch and validation receipt**.

### SRC-RP-STATEMENT-0005 — Build format and scope discipline: Core behavior

The Historical Patch Replay implementation SHALL provide the change remains minimal, formatted, buildable, and isolated to the unsafe read paths and their tests.

Acceptance intent: Demonstrate that repository formatting and relevant packages pass; all mandatory paths are covered by executable evidence.

### SRC-RP-STATEMENT-0011 — Build format and scope discipline: Input and state validation

The Build format and scope discipline capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, unrelated refactors and dependency changes are excluded.

### SRC-RP-STATEMENT-0017 — Build format and scope discipline: Interface contract

The public interfaces for Build format and scope discipline SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for small patch and validation receipt.

### SRC-RP-STATEMENT-0023 — Build format and scope discipline: Operator experience

The operator-facing workflow for Build format and scope discipline SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative maintainer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.

## SRC-RP-FEATURE-06 — Changelog and handoff

A concise unreleased changelog records user-visible behavior and the final evidence links the issue,
tests, files, and result.

Primary actor: **release maintainer**. Successful outcome: **the change can be reviewed and released from complete evidence**. Principal deliverable: **changelog and handoff evidence**.

### SRC-RP-STATEMENT-0006 — Changelog and handoff: Core behavior

The Historical Patch Replay implementation SHALL provide a concise unreleased changelog records user-visible behavior and the final evidence links the issue, tests, files, and result.

Acceptance intent: Demonstrate that the change can be reviewed and released from complete evidence; all mandatory paths are covered by executable evidence.

### SRC-RP-STATEMENT-0012 — Changelog and handoff: Input and state validation

The Changelog and handoff capability SHALL validate all externally supplied values and state preconditions before mutation, using explicit field- or state-level diagnostics.

Acceptance intent: Invalid, stale, or inconsistent inputs produce stable errors and no partial state; specifically, completion is not declared before regression evidence exists.

### SRC-RP-STATEMENT-0018 — Changelog and handoff: Interface contract

The public interfaces for Changelog and handoff SHALL use versioned, documented request, response, error, and event schemas with backward-compatible behavior inside the frozen benchmark scope.

Acceptance intent: Contract tests prove stable fields, status semantics, error codes, and artifact references for changelog and handoff evidence.

### SRC-RP-STATEMENT-0024 — Changelog and handoff: Operator experience

The operator-facing workflow for Changelog and handoff SHALL make state, progress, errors, required action, and authoritative evidence visible without requiring source-code inspection.

Acceptance intent: A representative release maintainer can complete the workflow and understand blocked, failed, and completed states using the documented UI or CLI.
