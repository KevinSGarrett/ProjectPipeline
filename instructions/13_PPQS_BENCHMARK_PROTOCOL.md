# PPQS Benchmark Protocol

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-13` |
| Status | `ACTIVE` |
| Pack version | `1.0.0` |
| Primary domains | `ppqs_benchmarks` |
| Governing entry point | `AGENTS.md` |

## Registered benchmark assets

The eight candidate-visible packs beneath `/dummy` are canonical benchmark seeds and are registered in `policies/PPQS_BENCHMARK_REGISTRY.json`:

1. PPQS-01 SchemaShift
2. PPQS-02 FieldDesk
3. PPQS-03 DemandForge
4. PPQS-04 Workcell Atlas
5. PPQS-05 Repository Safety Patch
6. PPQS-06 Inspector Release Replay
7. PPQS-07 Document Nexus
8. PPQS-08 Continuity Relay

Do not replace them with unrelated projects unless a pack is proven missing or invalid under its own manifest.

## Seed immutability

Before execution:

1. read only the pack manifest, brief, runtime contract, visible input manifest, and benchmark boundary;
2. verify declared pack integrity;
3. materialize a new isolated run workspace with run ID and source-pack digest;
4. keep the canonical pack read-only;
5. direct all candidate writes to declared `workspace/`, `candidate_outputs/`, or `run_logs/` inside the isolated copy;
6. preserve run evidence and final digest.

Intentional dirty repositories, empty logs, malformed files, fake canaries, failing tests, and conflicting requirements are test inputs. Do not clean the source pack.

## Oracle and hidden-evaluator prohibition

Candidate execution must never search for, list, open, infer from, or consume Oracle Packs, hidden tests, gold requirements, target solutions, evaluator scoring, private acceptance, or reference solutions. Visibility does not grant authority. An access attempt is a hard benchmark failure and contamination incident.

Do not use filenames, sibling directories, network locations, caches, prior run outputs, or model memory to infer hidden truth. Only candidate-visible inputs and ordinary public/project authority are allowed.

## Host repository validation boundary

PPQS files remain included in `PROJECT_MANIFEST.json` so deletion or mutation is detectable. Host placeholder scanning excludes `/dummy` because deliberate empty and nonbehavioral fixtures are benchmark data. Secret scanning remains active. The instruction validator verifies eight pack identities, required manifests, boundary declarations, and absence of candidate-visible Oracle directories.

This boundary is narrow: it does not hide missing pack files, broken boundaries, digest mismatch, undeclared mutation, or real secret leakage.

## Execution and scoring separation

ProjectPipeline candidate execution produces work and evidence without access to evaluator truth. Scoring/evaluation runs in a separate trust zone and consumes candidate outputs after execution. Candidate tools cannot mount evaluator-only paths.

## Test Jira and GitHub

Use clearly namespaced test resources, for example `PPQS-<ID>-<RUN-ID>`. Record owner, creation date, benchmark, evidence retention, reuse, and cleanup. Never mix benchmark state into the production `PP` Jira project or primary repository history.

## External acquisition packs

PPQS-05, 06, and 07 declare external acquisition requirements. Acquire only the candidate-visible declared target/revision through governed provenance and network policy. Do not substitute hidden evaluator repositories or unpinned content.

## Cleanup

Retain canonical packs, run manifests, outputs required for comparison, and evaluator evidence. Remove disposable isolated workspaces and remote test resources only after retention and unknown-outcome checks. Never delete evidence needed to reproduce a score.
