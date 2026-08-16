# UPSTREAM-095 — Bernstein orchestration and replay pattern review

## Decision

Bernstein remains a `MINE_IMPLEMENTATION_PATTERN` upstream. Project Pipeline does not adopt Bernstein as an orchestration authority or dependency. Pass 13 adopts bounded implementation patterns for deterministic replay, append-only run journaling, run receipts, lineage/audit integrity, and separation of orchestration control from agent execution.

## Inspected revision

`708ebf9b8acf8ced0e0bfb2a6e19b4be76c9defc`

## Source areas inspected

- `docs/operations/deterministic-replay.md`
- `docs/security/audit-log.md`
- `src/bernstein/core/replay/journal.py`
- `src/bernstein/core/replay/run_receipt.py`
- `src/bernstein/core/security/audit_chain.py`
- `src/bernstein/core/orchestration/orchestrator.py`

## Project Pipeline adoption

Project Pipeline uses its own domain and persistence model. The adopted patterns appear in:

- `src/project_pipeline/orchestration/persistence.py`
- `src/project_pipeline/orchestration/recovery.py`
- `src/project_pipeline/orchestration/service.py`
- `tests/test_orchestration_recovery.py`

The resulting contract records deterministic workflow events, persistent recovery decisions, immutable operation payload hashes, and explicit reconciliation for uncertain external outcomes. This is pattern reuse, not copied Bernstein source.

## License and provenance

GitHub reports Apache-2.0 for the inspected repository. No Bernstein source files are copied or vendored. Source incorporation remains `NOT_APPROVED`; only architecture/implementation patterns are adopted.
