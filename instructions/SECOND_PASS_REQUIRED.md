# Second-Pass External Activation and Verification Register

The repository-local instruction system is implemented in this pack. The items below cannot be truthfully marked live-verified from the exported snapshot or this execution environment. They require the named external access and must remain `BLOCKED_EXTERNAL` or `UNKNOWN` until evidence is collected.

## 1. Publish and protect the live GitHub repository

**Observed state:** `KevinSGarrett/ProjectPipeline` exists as a public repository, but it had no branches or repository content when inspected on 2026-08-16. The legacy underscored repository did not exist.

**Required second-pass actions after the first controlled push:**

1. verify `main` and the evaluated head SHA;
2. configure a ruleset or branch protection requiring pull requests, selected current status checks, conversation resolution where useful, and protection against force-push and deletion;
3. verify CodeQL, secret scanning, push protection, Dependabot, and dependency graph availability;
4. verify workflow permissions remain least privilege;
5. decide whether auto-merge is justified; do not enable a merge queue without observed concurrency need;
6. record screenshots or API responses as evidence.

**Authority:** `07`, `08`, `09`, `15`, `19`, and `policies/EXTERNAL_MUTATION_AUTHORITY.json`.

## 2. Reconcile the live Jira `PP` project

**Observed state:** the local mirror validates at 368 issues and 595 dependency/relationship edges. The connected Atlassian site was not explicitly granted to the available integration, so the remote project could not be read.

**Required second-pass actions:**

1. grant the intended Jira connector access to `kevinsgarrett.atlassian.net`;
2. take a read-only remote snapshot of project `PP`;
3. compare issue identities, statuses, hierarchy, dependencies, fields, and comments against the local mirror;
4. produce a reconciliation plan before any write;
5. apply only explicitly authorized operations with idempotency and unknown-outcome handling;
6. preserve the project rule that remote `DONE` requires the configured human gate.

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

**Observed state:** repository validation and all tests were executed in Linux/Python 3.13. The project is Windows-first, and the actual `C:\Project_X` host was not mounted.

**Required second-pass actions on Windows:**

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

Also exercise Windows-sensitive path, subprocess, worktree, remote-worker, and archive behavior.

## 6. Run unavailable optional quality and dependency tools

**Observed state:** Ruff, mypy, and pip-audit were not installed, and package-index access was unavailable. Their exact versions and CI commands are already pinned/configured.

**Required second-pass actions in an environment with dependency access:**

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
