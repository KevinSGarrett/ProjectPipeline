# PLAN-PDEF-002 Project Intake, Adoption, and Compilation

**Status:** ACTIVE  
**Authority:** `GOV-001:L000398-L000410`, `GOV-001:L001490-L001501`, `SRC-014:L000005-L000125`, `SRC-017:L001122-L001175`, `SRC-002:L000479-L000515`, `SRC-001:L001255-L001301`, `SRC-007:L000213-L000249`  
**Related plans:** `PLAN-PDEF-001`, `PLAN-REQ-002`, `PLAN-ARCH-001`, `PLAN-ARCH-004`, `PLAN-CTRL-001`, `PLAN-CTX-001`, `PLAN-GOV-001`, `PLAN-LIFE-001`, `PLAN-LIFE-002`, `PLAN-ASSURE-001`

## PLAN-PDEF-002:SEC-01 Purpose, authority, and intake modes

Project Intake and Project Compiler convert either a new project target or an existing repository into a deterministic, reviewable project-control manifest. The process is local-first, read-only during discovery, source-aware, profile-aware, idempotent for unchanged semantics, and explicit about everything it cannot safely infer.

Two intake modes are supported:

- `NEW_PROJECT` for an absent or empty target that requires controlled initialization;
- `EXISTING_PROJECT` for a repository that must be inventoried and baselined before any mutation.

The compiler does not execute discovered source code, build scripts, package hooks, repository instructions, or remote APIs. Discovered instructions are evidence to reconcile, not commands to obey automatically. The master source hierarchy, accepted decisions, and operator authorization remain above discovered repository content.

## PLAN-PDEF-002:SEC-02 Safe repository discovery and boundaries

Discovery resolves the target path without requiring it to exist for a new project. Existing-project intake requires a real directory. Filesystem roots, non-directories, upward traversal, and target escapes are rejected.

The scanner:

- walks in deterministic lexical order;
- never follows symbolic links;
- records links and whether their targets remain within the project root;
- does not traverse nested repositories unless explicitly enabled;
- excludes VCS internals, dependency caches, build outputs, local runtime state, virtual environments, and generated coverage directories;
- accepts configured limits for file count, aggregate bytes, and per-file hashing;
- hashes bounded regular files with SHA-256;
- records skipped hashes and parse failures as diagnostics;
- treats boundary crossings as explicit autonomy blockers.

Discovery is a read operation. It creates no target directories, local project files, branches, workflows, Jira items, remote resources, or external side effects.

## PLAN-PDEF-002:SEC-03 Instruction, plan, Jira, requirement, and environment discovery

The inventory identifies project authorities and operating surfaces by path and role, including:

- repository and version-control identity;
- instruction files and instruction directories;
- plans, specifications, and architecture documents;
- local Jira or equivalent work-management artifacts;
- machine-readable requirements;
- evidence and verification records;
- source, tests, documentation, configuration, build, CI, and deployment assets;
- recognized build systems, test commands, and deployment surfaces;
- secret-reference syntax counts without emitting secret values.

Recognized declarations are parsed only with data parsers. Python source is analyzed with the abstract syntax tree parser; JavaScript, TypeScript, Rust, and Go receive bounded lexical analysis. Malformed declarations become diagnostics and never trigger script execution.

## PLAN-PDEF-002:SEC-04 Project-profile detection and scale policy

Profile detection derives one primary profile and a bounded ordered set of supporting profiles from explicit operator selections and observed repository evidence. Supported profiles include generic, Python library, Python service, web application, TypeScript application, Rust application, machine learning, infrastructure, documentation, polyglot application, and empty target.

Profiles activate policy expectations rather than creating different directory contracts. Examples include Python lint/type/test gates, API contract tests for services, browser and accessibility checks for web applications, reproducibility and data-lineage controls for machine learning, and policy/cost/rollback checks for infrastructure.

Project scale is recorded independently as `SMALL`, `STANDARD`, `LARGE`, or `CRITICAL`. Scale changes review depth, evidence expectations, isolation, recovery rigor, and operational controls; it does not create incompatible project structures.

## PLAN-PDEF-002:SEC-05 Enriched repository map

The compiled repository map is a deterministic, content-addressed view of discovered files. For each entry it records, where available:

- repository-relative path;
- semantic role and detected language;
- size and SHA-256 digest;
- declared symbols;
- imported dependencies;
- source-to-test relationships;
- CODEOWNERS-derived owners;
- change-relevance categories.

Aggregate indexes include file count, total bytes, top-level counts, language counts, and role counts. The map fingerprint is derived from the ordered entry set and forms part of the compilation identity. It can later feed context compilation, conflict analysis, task scoping, review routing, and test selection without requiring full-repository context loading.

## PLAN-PDEF-002:SEC-06 Deterministic project-manifest compilation

Compilation combines the intake request, discovery, profile detection, repository map, and gap report into a strict `CompiledProjectManifest`. Its stable identity is derived from:

- resolved project identity;
- request semantic fingerprint;
- repository-map fingerprint;
- gap-report fingerprint;
- primary profile.

The manifest records repositories, project origin, intake mode, adoption stage, target root, scale, profiles, discovered authorities, build/test/deployment surfaces, operating constraints, source authorities, repository map, gaps, and compile timestamp. The timestamp is excluded from semantic equivalence, so repeated compilation of unchanged inputs produces the same compilation identity and semantic fingerprint.

Compilation outputs may be written as a four-document bundle containing the manifest, repository map, gap report, and summary. Existing differing output files are never replaced without an explicit replacement flag.

## PLAN-PDEF-002:SEC-07 Structured gap analysis and adoption state

Gap analysis compares discovered state against bounded baseline expectations. It reports stable gap identities, category, severity, affected paths, remediation, autonomy impact, and bootstrap eligibility. Checks include repository boundaries, potential credential-bearing files, overview documentation, instruction authority, plans, local work management, requirements, tests, CI, build declarations, licensing, malformed declarations, and greenfield state.

Existing-project adoption follows the staged model:

`DISCOVERY → BASELINE → GAP_ANALYSIS → ADOPTION_PLAN → CONTROLLED_BOOTSTRAP → SHADOW_AUTONOMY → LIMITED_AUTONOMY → FULL_AUTONOMY`

This implementation reaches deterministic gap analysis and controlled-bootstrap planning. It does not claim shadow, limited, or full autonomy. Those later stages require additional control, assurance, identity, policy, scheduling, and completion capabilities.

## PLAN-PDEF-002:SEC-08 Controlled non-destructive bootstrap

Bootstrap converts eligible gaps into deterministic actions. Dry-run is the default. Existing-project application requires explicit confirmation. Every action is one of create directory, create file, already satisfied, or conflict.

Safety requirements are:

- no deletes, renames, moves, branch changes, protection changes, remote writes, or workflow replacement;
- no overwrite of any differing existing file;
- exclusive file creation;
- repository-root confinement for every target path;
- profile-aware greenfield templates;
- authority-only templates for existing projects;
- rollback of files and empty directories created during a failed operation;
- machine-readable receipt with created, satisfied, conflicting, and rolled-back paths;
- repeated application against the same manifest yields no change after successful creation.

The bootstrap does not infer or install a legal license, credentials, cloud resources, live integrations, or project-specific business requirements.

## PLAN-PDEF-002:SEC-09 Persistence, CLI, and operator workflow

The local SQLite profile stores compiled manifests and bootstrap receipts through migration `PPDB-0003`. Compilation persistence is idempotent by compilation identity and semantic fingerprint. A collision with different semantics fails closed. Receipts use content-derived identities and retain actor, correlation, outcome, target, and timestamp.

The CLI supports:

- `intake inspect` for read-only discovery and profile detection;
- `intake compile` for manifest compilation, optional persistence, and optional bundle output;
- `intake map` and `intake gaps` for bounded projections;
- `intake bootstrap` for dry-run or explicitly authorized application;
- `intake status` for persisted compilation and receipt inspection.

Compilation occurs before opening persistence, preventing an operator-selected database inside the target from becoming an accidental input to its own discovery result. The PostgreSQL production boundary remains defined but is not represented as live verified.

## PLAN-PDEF-002:SEC-10 Verification, observability, recovery, and remaining boundaries

Verification covers strict models, stable identities, path confinement, discovery limits, non-executing parsing, symbolic-link handling, nested-repository policy, profile detection, repository-map enrichment, deterministic compilation, gap analysis, output replacement protection, greenfield bootstrap, existing-project confirmation, no-overwrite behavior, rollback, migration ordering, persistence idempotence, status queries, CLI errors, and repository self-validation.

Operational records include actor and correlation identities, compilation and bootstrap IDs, semantic fingerprints, diagnostics, gap severity counts, and receipt outcomes. Secret values are not logged or persisted by intake.

Recovery consists of removing only assets listed as created by a failed or explicitly rolled-back bootstrap, preserving all pre-existing content, and recreating local persistence from committed migrations when needed. Live GitHub, Jira, package-index, cloud, Windows-service, and production PostgreSQL verification remain outside this bounded implementation.
