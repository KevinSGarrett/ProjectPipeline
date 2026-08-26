# Dependency Management

`pyproject.toml` declares dependencies. Active runtime and test groups are captured in `requirements/environment.lock.json`, which records exact installed versions, dependency closure, and hashes of each distribution's `METADATA` file. The generated `runtime.txt` and `development.txt` files are deterministic pin exports from that lock.

The repository also records exact quality-tool intentions in `requirements/quality-tools.txt`. A cross-platform resolver-produced `uv.lock` is still required before release. It is intentionally not handwritten: the current execution environment cannot resolve package-index DNS, so `config/dependency_policy.json` records the resolver lock as `BLOCKED_EXTERNAL` and provides the activation and verification commands.

Commands:

```bash
PYTHONPATH=src python -m project_pipeline dependencies lock --root .
PYTHONPATH=src python -m project_pipeline dependencies validate --root . --verify-installed
python scripts/resolve_dependencies.py --portable
```

A dependency addition requires capability rationale, licensing/provenance review, an explicit activation group, tests at the removal boundary, and rollback instructions.

## Dependency PR Hygiene Controls

The repository enforces batched dependency intake to keep pull requests actionable and review capacity stable.

- Active dependency PR budget: at most `2` open `pip` PRs and `1` open `github-actions` PR at a time (via Dependabot open-PR limits).
- Batching cadence: weekly on Monday in controlled windows; patch and minor updates are grouped per ecosystem.
- Major-version containment: noisy GitHub Action major bumps are ignored by default and handled in explicit maintenance batches.
- Closure/supersede protocol: when flood or overlap occurs, close superseded Dependabot PRs with one policy rationale comment and retain the local queue in `.local/evidence/dependency_pr_queue.json` so no update is lost.
- Active PR budget: keep only feature/product PRs and at most one dependency batch per ecosystem concurrently; if exceeded, pause intake and escalate in the next planning checkpoint before reopening dependency flow.
