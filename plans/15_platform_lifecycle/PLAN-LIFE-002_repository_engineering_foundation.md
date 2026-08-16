# PLAN-LIFE-002 Repository Engineering Foundation

**Status:** ACTIVE  
**Authority:** `GOV-001:L001463-L001475`, `GOV-001:L000880-L000945`, `GOV-001:L001219-L001285`, `GOV-001:L001319-L001385`, `GOV-001:L002199-L002231`  
**Related plans:** `PLAN-ARCH-002`, `PLAN-GOV-001`, `PLAN-ASSURE-001`, `PLAN-OPS-001`, `PLAN-SEC-001`, `PLAN-UPSTREAM-002`

## PLAN-LIFE-002:SEC-01 Purpose and engineering outcomes

The repository engineering foundation turns the accepted architecture into an installable, typed, self-validating Python package without introducing premature services. It establishes one practical source layout, one configuration authority, explicit dependency states, versioned contracts, correlation-aware telemetry, deterministic bootstrap commands, and local quality gates.

Required outcomes are:

- imports resolve from the `src/` package rather than the repository root;
- active dependencies have exact locally verified versions and provenance evidence;
- unavailable resolver or tool access remains explicit rather than being replaced by fabricated artifacts;
- configuration rejects unknown fields and never stores secret values;
- command, event, transition, diagnostic, and adapter-error payloads are versioned and machine-validatable;
- local command execution demonstrates idempotency and immutable artifact integrity;
- the CLI provides bounded diagnostics, configuration, schema, dependency, smoke, quality, and validation operations;
- CI defines the same required checks that developers run locally;
- all completed claims link to tests and evidence.

## PLAN-LIFE-002:SEC-02 Practical source and package boundaries

The executable package remains a modular monolith under `src/project_pipeline/`. Subpackages own distinct semantics:

- `configuration` owns layered settings, profiles, secret references, and configuration schema validation;
- `contracts` owns versioned Pydantic models and deterministic JSON Schema export;
- `core` owns command processing, results, errors, and the local idempotency journal;
- `observability` owns correlation context, structured logging, redaction, and the OpenTelemetry provider boundary;
- `runtime` composes diagnostics and executable smoke verification;
- existing architecture, requirement, Jira, evidence, artifact, upstream, and repository-validation modules remain authoritative for their established data.

Dependencies between these packages flow toward contracts and ports. No runtime package may import continuation/session-state materials, and external-provider semantics remain behind ports.

## PLAN-LIFE-002:SEC-03 Dependency declaration, locking, and activation

`pyproject.toml` is the declaration authority. Dependency groups are separated by lifecycle:

- `runtime` and `group:test` are active and must be represented in the observed-environment lock;
- API, database, OTLP, and quality groups remain declared but activation-gated until their dependencies and operational prerequisites can be resolved and verified;
- dependency source incorporation remains a separate decision from package activation.

The active lock records exact versions, applicable dependency closure, and SHA-256 hashes of installed distribution metadata. Deterministic pin exports are generated from that lock. A cross-platform resolver-produced `uv.lock` remains required before release; if package-index metadata is unavailable, the resolver state is `BLOCKED_EXTERNAL` with an activation command and verification method. Handwritten resolver output is prohibited.

Every dependency addition requires:

1. a capability rationale;
2. a removal boundary;
3. license and provenance review;
4. activation state;
5. compatibility and regression tests;
6. rollback instructions.

## PLAN-LIFE-002:SEC-04 Typed configuration and secret references

Configuration precedence is deterministic:

1. committed base configuration;
2. selected committed profile;
3. optional explicit JSON configuration;
4. `.env` and process environment values;
5. explicit CLI overrides.

Pydantic models use `extra=forbid`, immutable instances, and validated defaults. Paths remain relative to the project root unless intentionally absolute. External writes default to denied or dry-run behavior and require explicit approval authority.

Secret-bearing settings accept references only. Supported reference forms are `env://NAME` and repository-confined `file://relative/path`. Secret resolution is demand-driven, never included in configuration fingerprints, and never emitted to logs or generated configuration artifacts.

## PLAN-LIFE-002:SEC-05 Versioned contracts and generated schemas

The contract boundary includes:

- action intent;
- command envelope and result;
- state transition;
- event envelope;
- adapter error payload;
- diagnostic snapshot;
- runtime configuration;
- secret reference.

Contracts reject unknown fields, use timezone-aware UTC timestamps, carry correlation and idempotency identities, and encode error/retry/unknown-outcome semantics. Generated JSON Schemas use Draft 2020-12, stable filenames, schema identifiers, and deterministic formatting. Repository validation fails when a committed schema differs from its authoritative model.

## PLAN-LIFE-002:SEC-06 Structured logging and telemetry foundation

Correlation context carries project, workflow, task, run, actor, correlation, and causation identifiers. Structured JSON logging merges this context with trace identifiers and event attributes. Configured sensitive-field markers and secret types are redacted recursively; byte values are summarized instead of emitted.

OpenTelemetry is the portable tracing boundary. A local provider can be created without a remote exporter. OTLP export is profile-gated and cannot be enabled without an endpoint. Telemetry failure is observational and cannot become deterministic workflow authority.

## PLAN-LIFE-002:SEC-07 Bootstrap and executable core slice

Bootstrap diagnostics verify:

- supported Python version;
- repository root availability;
- active runtime dependencies;
- runtime-path writability or preparability;
- safe external-write defaults;
- telemetry state;
- optional quality-tool availability;
- repository contract when requested.

The executable core slice submits a typed command through a registered handler, writes an atomic idempotency journal record, emits a typed transition and event, replays the same semantic command without calling the handler again, stores evidence bytes in the content-addressed artifact store, and verifies their digest. Different semantics under the same idempotency key fail closed.

## PLAN-LIFE-002:SEC-08 Quality gates and CI

Required local and CI checks are:

- Python compilation;
- behavioral tests;
- branch-aware coverage threshold;
- generated-schema validation;
- dependency-state validation;
- repository self-validation;
- Ruff lint and format verification;
- strict Mypy verification for the new executable packages;
- package build;
- runtime dependency vulnerability audit.

Local environments may report optional tools unavailable when strict mode is not requested. CI treats configured quality tools as required. CI uses read-only repository permissions, bounded timeouts, matrix Python versions, and preserves audit evidence when available.

## PLAN-LIFE-002:SEC-09 Developer setup and operating commands

Portable and PowerShell bootstrap scripts set `PYTHONPATH`, prepare runtime paths, validate active dependency state and generated schemas, and run tests. They perform no external Project Pipeline integration mutation.

Primary commands are:

- `project-pipeline doctor` for bounded prerequisite inspection;
- `project-pipeline config validate` for effective configuration and fingerprinting;
- `project-pipeline bootstrap --prepare` for local runtime preparation;
- `project-pipeline smoke` for the executable foundation journey;
- `project-pipeline dependencies lock|validate|status|snapshot` for dependency evidence;
- `project-pipeline schemas write|check` for contract schemas;
- `project-pipeline quality` for local quality orchestration;
- `project-pipeline validate` for repository-wide self-audit.

## PLAN-LIFE-002:SEC-10 Verification, evidence, and rollback

Completion requires behavioral tests for configuration precedence, secret confinement, contract invariants, redaction, context restoration, idempotent replay, semantic-key conflict, runtime preparation, smoke integrity, dependency lock determinism, and CLI behavior.

Evidence records must contain command output or generated validation artifacts and their hashes. Runtime state under `.local/` is excluded from the permanent repository and removed before manifest generation and packaging.

Rollback consists of reverting the package/configuration changes, restoring the prior manifest, and removing generated runtime state. Dependency activation can be rolled back independently because optional integrations and quality tools do not own deterministic domain semantics.

## PLAN-LIFE-002:SEC-11 Remaining boundaries

This foundation does not claim completion of persistent PostgreSQL state, durable workflow activation, scheduler semantics, remote Jira/GitHub writes, Command Center services, Windows packaging, AWS deployment, or remote telemetry export. Those capabilities remain governed by their dedicated plans and acceptance gates.
