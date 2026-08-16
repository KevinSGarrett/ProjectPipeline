
# Contributing

Read `AGENTS.md` and route the change through `instructions/INSTRUCTION_COVERAGE_MATRIX.json` before editing. The numbered instruction for the active domain and its machine-readable policies are part of the contribution contract.

## Core rules

1. Preserve source provenance for every source-derived requirement.
2. Use stable IDs for plans, sections, requirements, decisions, work items, acceptance criteria, tests, and evidence.
3. Update implementation and verification together.
4. Never mark a work item complete solely because code exists.
5. Keep external mutation disabled unless the action is explicitly authorized.
6. Prefer small, semantically named files over monolithic documents.
7. Preserve backward traceability from code and tests to requirement and source.
8. Preserve unknown or dirty work before cleanup and reconcile uncertain external writes before retry.
9. Keep credentials, `.env`, Codex/session state, local databases, upstream clones, and generated release archives out of commits.

## Branch and review contract

Use short-lived branches with names that include the local work-item ID, for example:

```text
feature/PP-TASK-000001-repository-validator
fix/PP-BUG-000001-jira-parent-check
```

A pull request should identify:

- work-item IDs;
- requirement IDs;
- affected plans and decisions;
- acceptance criteria;
- test and evidence locations;
- security and operational impact;
- rollback or recovery considerations.

## Local quality gate

PowerShell on the supported Windows development path:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\validate_instructions.py --root .
.\.venv\Scripts\python.exe scripts\instruction_cold_start.py --root .
.\.venv\Scripts\python.exe -m project_pipeline doctor --root .
.\.venv\Scripts\python.exe -m project_pipeline validate --root .
.\.venv\Scripts\python.exe -m project_pipeline jira validate --root .
.\.venv\Scripts\python.exe -m pytest -q
```

Run the additional tier-specific checks in `instructions/policies/CI_RISK_MATRIX.json`. The repository validator is authoritative for repository-contract checks, but a clean test run does not replace acceptance-criterion evidence or the deterministic Completion Gate.
