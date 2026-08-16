# Second-Pass External Activation and Verification Register

The repository-local instruction system is implemented in this pack. This register records both completed live verification and work that still requires external access. An item remains `BLOCKED_EXTERNAL` or `UNKNOWN` until the named evidence is collected; completed observations are dated and identify the evidence boundary.

## 1. Publish and protect the live GitHub repository

**Status:** `UNKNOWN` pending durable evidence-ledger registration. The observations below were made on 2026-08-16 but are not yet independently verifiable from a cold clone.

**Observed state:** `KevinSGarrett/ProjectPipeline` is a populated public repository with protected `main`. API readback verified required pull requests and status checks, conversation resolution, linear history, and force-push/deletion protection. CodeQL, secret scanning, push protection, Dependabot, dependency graph, and least-privilege workflow permissions were verified during the controlled publication sequence. Exact-head pull-request checks and post-merge `main` checks were preserved as GitHub evidence; the current instruction-maintenance change remains subject to the same protected merge gate.

**Observed actions pending evidence registration:**

1. verified `main` and each evaluated pull-request head SHA before merge;
2. configured and read back branch protection requiring pull requests, selected current status checks, conversation resolution, linear history, and protection against force-push and deletion;
3. verified CodeQL, secret scanning, push protection, Dependabot, and dependency graph availability;
4. verified workflow permissions remain least privilege;
5. retained manual protected merging; no merge queue or auto-merge was enabled without an observed concurrency need;
6. retained GitHub API responses and exact-head check runs as evidence.

**Authority:** `07`, `08`, `09`, `15`, `19`, and `policies/EXTERNAL_MUTATION_AUTHORITY.json`.

## 2. Reconcile the live Jira `PP` project

**Status:** `UNKNOWN` pending durable evidence-ledger and applicable Jira-reference registration. The read, plan, bounded write, readback, and recovery observations below were made on 2026-08-16.

**Observed state:** the local Jira mirror validates at 378 issues and 605 dependency/relationship edges. Authenticated read-only snapshots of the live `PP` project were captured. The READY and IN_PROGRESS reconciliations were applied with receipts and complete readbacks. The REVIEW reconciliation produced a deterministic partial receipt, `JREC-072E9A714667ACFF42C5`: its field update applied, its unsupported `Code Review` transition failed with no unknown outcome, and snapshot `JSNAP-BB122CAF17909D8EE034` confirmed PP-318 remained remotely `In Progress`. The policy was then corrected to project rich local lifecycle states onto the live three-state Jira workflow (`To Do`, `In Progress`, `Done`) while retaining the human gate for remote `Done`.

**Observed actions pending evidence registration:**

1. authenticated the governed Jira adapter for `kevinsgarrett.atlassian.net` without persisting credentials in the public tree;
2. captured complete read-only snapshots of project `PP`;
3. compared issue identities, statuses, hierarchy, dependencies, and governed fields against the local mirror;
4. generated immutable reconciliation plans before every write;
5. applied only explicitly authorized operations and preserved receipts, readbacks, idempotency keys, and deterministic failure evidence without retrying an unchanged failed operation;
6. preserved the rule that remote `Done` requires the configured human gate.

**Authority:** `06`, `15`, `17`, and `config/jira/sync_policy.json`.

## 3. Inspect the live upstream-repository workspace

**Observed state:** the export did not contain `C:\Project_X\Github_Repo\used_repos` or `github_repo_urls.txt`. The source-controlled registry and 116 completed upstream reviews were inspected, and current expected paths were normalized to the governing root.

**Required second-pass actions on the Windows host:**

1. inventory `C:\Project_X\Github_Repo\used_repos` without executing repository code;
2. compare the URL catalog, local repository names, revisions, and licenses with `provenance/upstream_registry.json`;
3. record missing, extra, moved, or revision-drifted repositories;
4. update provenance through canonical tooling rather than fabricating contents;
5. keep source incorporation blocked until the Upstream Adoption Gate passes.

**Authority:** `14_UPSTREAM_REPOSITORY_PROTOCOL.md`.

## 4. Qualify the secondary CPU worker

**Observed state:** the declared worker identity is `COMFY-V4-CPU-01`, with Chrome Remote Desktop alias `FIVERR-AI-RUNNER`. No secure execution channel or live capability profile was accessible.

**Required second-pass actions:**

1. establish and authenticate a scriptable channel such as SSH, PowerShell Remoting, WinRM, or a bounded ProjectPipeline worker;
2. capture OS, CPU, RAM, tools, workspace, heartbeat, and fencing capability;
3. run a read-only health check and a disposable bounded test job;
4. verify independent clone/worktree ownership and artifact transfer;
5. exercise worker-loss recovery before accepting production dispatch.

**Authority:** `16`, `17`, `policies/MACHINE_REGISTRY.json`.

## 5. Execute Windows-native validation

**Status:** `UNKNOWN` pending durable evidence-ledger registration. The Windows observations below were made on 2026-08-16.

**Observed state:** Windows-native validation ran from the canonical `C:\Project_X` workspace and governed Windows worktrees. The instruction validator and cold start, repository and Jira validators, control commands, full pytest suite, Windows-sensitive path/worktree behavior, and protected Git/GitHub workflow were exercised. The latest policy-repair full suite passed with 726 tests, 1 environment-appropriate symlink skip, and 6 subtests; repository validation reported 41 checks with 0 errors and 0 warnings, and Jira validation reported 378 issues, 605 edges, 0 errors, and 0 warnings.

**Executed command set pending evidence registration:**

```powershell
$env:PYTHONPATH = "src"
python -m project_pipeline doctor --root .
python scripts/validate_instructions.py --root .
python scripts/instruction_cold_start.py --root .
python -m project_pipeline validate --root .
python -m project_pipeline jira validate --root .
python -m project_pipeline control evaluate --root .
python -m project_pipeline control sequence --root .
python -m pytest -q
```

Windows-sensitive path, subprocess, and worktree behavior were exercised. Live secondary-worker qualification remains separately blocked under item 4; that outstanding external capability is not implied by this local validation result.

## 6. Run unavailable optional quality and dependency tools

**Status:** `UNKNOWN` pending durable evidence-ledger registration. The governed local and hosted quality-lane observations below were made on 2026-08-16.

**Observed state:** pinned quality dependencies were installed through the authoritative dependency policy and generated exports. Ruff check/format, configured strict mypy, dependency audit, build/test validation, and hosted Python 3.11/3.13 verification ran successfully. The current Jira-policy repair also passed Ruff and targeted no-incremental mypy for its changed runtime module; `scripts/validate_instructions.py` remains outside the configured source typing lane and is validated by its dedicated instruction tests and transactional validator.

**Executed quality command set pending evidence registration:**

```powershell
python -m pip install -r requirements/quality-tools.txt
ruff check src tests
ruff format --check src tests
mypy
pip-audit --local
python -m build
```

A failure must be corrected and revalidated; tool unavailability is not a passing result.

## Completion rule

No item above may be described as live-verified until its evidence exists. External activation does not require redesigning the instruction pack unless the live system reveals a real authority or compatibility conflict. After completing these actions, update this register, the evidence ledger, and applicable Jira state through the normal Completion Gate.
