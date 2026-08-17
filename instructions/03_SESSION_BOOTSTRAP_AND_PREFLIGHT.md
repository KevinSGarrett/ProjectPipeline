# Session Bootstrap and Preflight

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-03` |
| Status | `ACTIVE` |
| Pack version | `1.2.0` |
| Primary domains | `preflight`, `windows_compatibility` |
| Governing entry point | `AGENTS.md` |

## Objective

Determine the real repository, tool, Git, project-control, Jira, and validation state before designing or editing. Preflight is diagnostic; a red result is not automatic permission to change production code.

## Repository identity check

Confirm these paths exist: `AGENTS.md`, `instructions/INSTRUCTION_MANIFEST.json`, `config/project.json`, `plans/PLAN_CATALOG.json`, `jira/BOARD_MANIFEST.json`, `src/project_pipeline/cli.py`, and `tests`.

Read `config/project.json` and `config/project_manifest.json`. Expected identity is `ProjectPipeline`, `PROJECT-PIPELINE`, `KevinSGarrett/ProjectPipeline`, and `C:\Project_X`.

## Canonical commands

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m project_pipeline doctor --root .
python -m project_pipeline validate --root .
python -m project_pipeline jira validate --root .
python -m project_pipeline control evaluate --root .
python -m project_pipeline control sequence --root .
python scripts/validate_instructions.py --root .

git status --short --branch
git branch -vv
git worktree list
git remote -v
```

Bash-compatible shell:

```bash
export PYTHONPATH=src
python -m project_pipeline doctor --root .
python -m project_pipeline validate --root .
python -m project_pipeline jira validate --root .
python -m project_pipeline control evaluate --root .
python -m project_pipeline control sequence --root .
python scripts/validate_instructions.py --root .

git status --short --branch
git branch -vv
git worktree list
git remote -v
```

Inspect open PRs and live GitHub/Jira state only when credentials, network, and authorization permit. Read-only failure does not authorize a write workaround.

## Failure classification

Classify every issue before editing:

- implementation defect;
- stale generated artifact or manifest;
- intentional benchmark fixture;
- negative test fixture;
- intentionally dirty PPQS seed;
- missing optional tool;
- externally blocked verification;
- exported-snapshot limitation;
- packaging artifact;
- repository corruption;
- security incident.

Record the classification, evidence, affected scope, and next action. A benchmark seed must not be normalized to make host validation green.

## Snapshot versus Git checkout

If `.git` is absent, Git commands will correctly report that the directory is not a repository. Mark branch, worktree, and remote observations `SNAPSHOT_NOT_GIT_CHECKOUT`. Continue file-level inspection and validation. Do not create synthetic Git history or claim a clean branch.

When `.git` exists, inspect dirty state and ownership before any branch, reset, cleanup, or worktree operation. Use Repository Steward commands for governed changes.

## Tool availability

`doctor` distinguishes required failures from optional unavailable tools. Install or activate an optional tool only when authorized and needed for the current verification. Do not claim the check ran when the tool was absent. A missing release verifier can block release even when a missing optional formatter does not block analysis.

## Generated-state checks

Compare machine-readable registries to narrative counts. When derived artifacts are stale, identify their generator and scope. Typical generators are `requirement-views`, `jira-rebuild`, `line-plans`, `coverage`, `map`, `schemas`, and `manifest`.

Regenerate only after authoritative inputs are stable. Remove untracked runtime outputs such as `.local`, build directories, coverage files, or caches before generating permanent manifests.

## Windows-first verification

ProjectPipeline must remain meaningful on Windows. Use portable `pathlib` paths, safe subprocess argument arrays, and documented platform differences. Linux CI is not proof of Windows-sensitive behavior. For path, process, shell, filesystem, service, or desktop changes, include applicable Windows validation or record it as blocked.

## Preflight completion record

A session checkpoint records timestamp, repository root, Git state or snapshot limitation, validator results, Jira count and graph state, control completion state, ready count, optional tools, external-system reachability, active workers, and next eligible action. Use `templates/SESSION_CHECKPOINT.md`.
