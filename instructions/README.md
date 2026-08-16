# ProjectPipeline Instruction System

This directory is the routed operating system for autonomous ProjectPipeline development. `AGENTS.md` is the concise always-loaded entry point; these files contain the domain details, machine-readable policy, reusable procedures, templates, and validation required for a new Codex session to work without prior conversation history.

## Consumption order

1. `AGENTS.md`
2. `00_START_HERE.md`
3. `01_AUTHORITY_AND_SOURCE_OF_TRUTH.md`
4. `03_SESSION_BOOTSTRAP_AND_PREFLIGHT.md`
5. the single primary file for the active domain in `INSTRUCTION_COVERAGE_MATRIX.json`
6. only the targeted project records required by the context route

## Structure

- `00` through `20` are human/AI operating instructions with one primary owner per domain.
- `INSTRUCTION_MANIFEST.json` versions and hashes the instruction system.
- `INSTRUCTION_COVERAGE_MATRIX.json` prevents competing policy locations.
- `AUTHORITY_MAP.json` encodes normative and observational authority.
- `policies/` contains machine-readable decision matrices.
- `schemas/` validates the core instruction metadata.
- `templates/` standardizes work claims, interventions, pull requests, checkpoints, and handoff.
- `examples/` demonstrates cold start and scenario behavior.
- `SECOND_PASS_REQUIRED.md` records external activation and verification that could not be evidenced from the exported snapshot.
- `/.agents/skills/` contains repeated bounded procedures, not duplicate policy.
- `/scripts/validate_instructions.py` validates this system.
- `/scripts/instruction_cold_start.py` prints a no-chat cold-start route.

## Canonical validation

```bash
PYTHONPATH=src python scripts/validate_instructions.py --root .
PYTHONPATH=src python scripts/instruction_cold_start.py --root .
PYTHONPATH=src python -m project_pipeline validate --root .
PYTHONPATH=src pytest -q tests/test_instruction_system.py
```

The validator checks required files, IDs, hashes, coverage ownership, authority structure, internal links, secrets, stale paths, action pinning, PPQS boundaries, scenario coverage, and root entry-point size.

## Change control

Instruction and control-policy changes are high-impact self-modification under `config/security_policy.json`. Follow `20_INSTRUCTION_MAINTENANCE.md`, update the manifest hashes, run cold-start and scenario checks, require independent review, and retain rollback material.
