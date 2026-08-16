# Project Intake and Compilation

Project Pipeline can inspect a project root, classify its operating profile, compile a deterministic repository map and gap report, persist the compilation, and prepare a bounded bootstrap plan. Intake supports both greenfield projects and adoption of existing repositories.

The intake subsystem is intentionally conservative:

- discovery is read-only and does not execute repository code, hooks, package scripts, or instructions;
- symlinks are inventoried but never traversed;
- all paths are resolved relative to the selected project root and root escape is rejected;
- secret-like values are never copied into compilation artifacts;
- existing files are never overwritten by bootstrap;
- external systems are never mutated by intake;
- adoption stops at discovery, baseline, gap analysis, and a controlled bootstrap plan unless later authority explicitly advances the project.

## Commands

Inspect a project without creating a database or generated bundle:

```bash
PYTHONPATH=src python -m project_pipeline intake inspect \
  --target-root /path/to/project \
  --mode EXISTING_PROJECT \
  --project-name "Example Project"
```

Compile and persist an intake record in the local projection:

```bash
PYTHONPATH=src python -m project_pipeline intake compile \
  --root . \
  --target-root /path/to/project \
  --mode EXISTING_PROJECT \
  --project-name "Example Project" \
  --write-bundle /path/to/review/intake
```

Query a persisted compilation:

```bash
PYTHONPATH=src python -m project_pipeline intake status --root .
PYTHONPATH=src python -m project_pipeline intake map --root . --compilation-id COMP-...
PYTHONPATH=src python -m project_pipeline intake gaps --root . --compilation-id COMP-...
```

Generate a dry-run bootstrap plan:

```bash
PYTHONPATH=src python -m project_pipeline intake bootstrap \
  --root . \
  --target-root /path/to/project \
  --mode EXISTING_PROJECT \
  --project-name "Example Project"
```

Apply only after reviewing the plan and providing explicit confirmation:

```bash
PYTHONPATH=src python -m project_pipeline intake bootstrap \
  --root . \
  --target-root /path/to/project \
  --mode EXISTING_PROJECT \
  --project-name "Example Project" \
  --apply \
  --confirmation "APPLY_BOOTSTRAP"
```

See [Safe discovery](safe_discovery.md), [Compilation model](compilation.md), and [Controlled bootstrap](bootstrap.md) for behavior and safety details.
