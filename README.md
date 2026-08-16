# ProjectPipeline

ProjectPipeline is a local-first, optionally cloud-assisted control system for compiling software-project intent into traceable requirements, governed work, isolated execution, verified evidence, and an operator-visible completion state.

The repository is designed for two audiences at once:

1. engineers who need a conventional, maintainable software project; and
2. autonomous workers that need compact indexes, stable identifiers, explicit authority, deterministic validation, and bounded context.

## Current repository state

The repository currently contains a source-grounded and executable engineering foundation with:

- **351 atomic requirements** across all 18 planning domains;
- **1,109 canonical source-section dispositions**, including duplicate and prefix-overlap handling;
- **32 registered decisions**, **15 source-evolution records**, and a **62-term glossary**;
- **29 technical plans** with **196 stable, line-addressable sections**;
- **378 structured Jira work items** and **605 deterministic relationship edges**;
- more than **690 behavioral test functions** across the repository;
- **174 evidence ledger records** with criterion-specific status retained in the ledger;
- strict domain identifiers, requirement entities, project and task state, reversible migrations, transactional bidirectional traceability, and migration-backed intake compilation;
- an executable SQLite local state profile with PostgreSQL production-oriented DDL behind a replaceable persistence port;
- safe project discovery, deterministic profile and repository-map compilation, structured gap analysis, and controlled bootstrap;
- a typed Jira Steward with local mirror validation, deterministic reconciliation, transactional outbox state, mock and Jira Cloud adapters, governed comments and transitions, import/export, and dry-run CLI operations;
- a Repository/GitHub Steward with safe local Git inspection, branch/worktree ownership, Branch Guardian, pull-request/review/check models, Merge Gate, provider-neutral GitHub adapters, and unknown-outcome reconciliation;
- a deterministic Project Control Kernel and Build Sequencer with dependency-DAG validation, eligibility/readiness computation, critical-path/slack analysis, priority ranking, scope reconciliation, completion projection, persistent snapshots, and approval-gated readiness transitions;
- query, regeneration, validation, schema, manifest, repository-map, and archive tooling.

The Project Control Kernel is partially implemented and the Build Sequencer is implemented for dependency/readiness/priority analysis. Conflict-safe parallel lane scheduling, resource governance, agent routing, durable orchestration, Command Center, and live external integrations are not represented as finished. Their accepted requirements and implementation paths remain recorded in `/plans`, `/jira`, and the traceability registries.

## Authority model

ProjectPipeline separates deterministic control from probabilistic recommendation. Machine-generated recommendations may propose work, context, routing, or review findings, but they may not silently override canonical plans, requirements, policy, dependency state, evidence, or completion gates.

The source-of-truth order is recorded in [`plans/00_project_definition/PLAN-PDEF-001_project_definition.md`](plans/00_project_definition/PLAN-PDEF-001_project_definition.md).

## Repository map

- `plans/` — indexed technical planning corpus and traceability registries
- `jira/` — structured local work-management mirror and relationship graph
- `adr/` — architecture decision records
- `src/project_pipeline/` — executable registry, query, generation, and repository-audit tooling
- `tests/` — executable contract, graph, archive, source, and traceability tests
- `schemas/` — machine-readable data contracts
- `contracts/` — cross-component behavioral contracts
- `provenance/` — source and upstream-candidate registries
- `evidence/` — verification outputs and evidence ledger
- `scripts/` — portable command wrappers
- `docs/` — navigation, development, and operational guidance
- `runbooks/` — repeatable operational procedures

A generated compact map is available at [`docs/generated/REPOSITORY_MAP.json`](docs/generated/REPOSITORY_MAP.json). Requirement-catalog usage is documented in [`docs/REQUIREMENT_CATALOG.md`](docs/REQUIREMENT_CATALOG.md).

## Local bootstrap

From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m project_pipeline doctor --root .
python -m project_pipeline validate --root .
python -m pytest -q
```

On Bash-compatible systems:

```bash
PYTHONPATH=src python -m project_pipeline doctor --root .
PYTHONPATH=src python -m project_pipeline validate --root .
PYTHONPATH=src python -m pytest -q
```


## Project intake and compilation

Inspect a new or existing project without executing repository content or changing external systems:

```bash
PYTHONPATH=src python -m project_pipeline intake inspect \
  --target-root /path/to/project \
  --mode EXISTING_PROJECT \
  --project-name "Example Project"
```

Compile and optionally persist a deterministic manifest, repository map, profile set, and gap report:

```bash
PYTHONPATH=src python -m project_pipeline intake compile \
  --root . \
  --target-root /path/to/project \
  --mode EXISTING_PROJECT \
  --project-name "Example Project"
```

Bootstrap remains dry-run unless explicitly applied and confirmed. Existing files are never overwritten. See [`docs/intake/README.md`](docs/intake/README.md).

## Core state and transactional traceability

Initialize an isolated local projection without changing any external system:

```bash
PYTHONPATH=src python -m project_pipeline state init --root .
PYTHONPATH=src python -m project_pipeline state status --root .
PYTHONPATH=src python -m project_pipeline trace-store requirement --root . --requirement-id REQ-ARCH-0008
PYTHONPATH=src python -m project_pipeline trace-store source --root . --source-reference SRC-003:L000962-L001001
```

The local database lives beneath `.local/`, which is excluded from permanent manifests and archives. The validated repository registries remain authoritative; traceability mutations are persisted as proposed changes and require explicit export and review before source catalogs can change. See [`docs/data/README.md`](docs/data/README.md).

## Jira Steward

Validate, export, diff, and dry-run the Jira synchronization model without remote mutation:

```bash
PYTHONPATH=src python -m project_pipeline jira validate --root .
PYTHONPATH=src python -m project_pipeline jira export --root . --output .local/exports/jira_mirror.json
PYTHONPATH=src python -m project_pipeline jira plan --root . --provider mock --output .local/jira/plan.json
PYTHONPATH=src python -m project_pipeline jira sync --root . --provider mock
```

The Jira Cloud adapter is isolated behind a typed provider port. Live writes remain denied by default, require an approved action intent and authorization identifier, and halt for reconciliation after an unknown write outcome. See [`docs/jira/README.md`](docs/jira/README.md).


## Project Control and build sequencing

Evaluate canonical work state and inspect deterministic sequencing without mutating external systems:

```bash
PYTHONPATH=src python -m project_pipeline control evaluate --root .
PYTHONPATH=src python -m project_pipeline control sequence --root .
PYTHONPATH=src python -m project_pipeline control scope --root .
PYTHONPATH=src python -m project_pipeline control completion --root .
PYTHONPATH=src python -m project_pipeline control ready-plan --root .
```

`ready-apply` requires both explicit apply and approval flags and uses optimistic task-state versions. The control projection cannot satisfy the independent final Completion Gate. See [`docs/control/project_control_kernel.md`](docs/control/project_control_kernel.md).

## Requirement retrieval and regeneration

Summarize or search the atomic catalog without loading the complete corpus:

```bash
PYTHONPATH=src python -m project_pipeline requirements --root . --summary
PYTHONPATH=src python -m project_pipeline requirements --root . --id REQ-CTX-0007
PYTHONPATH=src python -m project_pipeline requirements --root . --domain SEC --priority P0
PYTHONPATH=src python -m project_pipeline requirements --root . --source SRC-017 --text evidence
```

Regenerate deterministic derived artifacts after changing authoritative records:

```bash
PYTHONPATH=src python -m project_pipeline requirement-views --root .
PYTHONPATH=src python -m project_pipeline jira-rebuild --root .
PYTHONPATH=src python -m project_pipeline line-plans --root .
PYTHONPATH=src python -m project_pipeline coverage --root .
PYTHONPATH=src python -m project_pipeline map --root .
PYTHONPATH=src python -m project_pipeline manifest --root .
```

Create and verify a release archive:

```bash
PYTHONPATH=src python -m project_pipeline archive --root . --output ../ProjectPipeline.zip
PYTHONPATH=src python -m project_pipeline verify-archive --archive ../ProjectPipeline.zip --expected-root ProjectPipeline
```

## Safety defaults

External mutation is denied by default. GitHub, Jira, cloud, provider, purchasing, and deployment operations require an explicit action intent, authorization, and the necessary credentials. Generated files contain no operational secrets.

## Status semantics

Implementation records use these states:

- `IMPLEMENTED`
- `PARTIALLY_IMPLEMENTED`
- `MOCK_VERIFIED`
- `LIVE_VERIFIED`
- `BLOCKED_EXTERNAL`
- `PLANNED_ONLY`

Unknown information remains unknown. A plan, ticket, or generated statement is not completion evidence.
