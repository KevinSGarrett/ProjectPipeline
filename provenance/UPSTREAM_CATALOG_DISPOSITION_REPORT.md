# Upstream Catalog Disposition Report

Catalog repositories: `116`
Terminal dispositions: `116`
Vague `EVALUATE_LATER` entries: `0`

## Disposition counts

- `ADAPT_COMPONENT`: `14`
- `ADOPT_DEPENDENCY`: `48`
- `MINE_ARCHITECTURE`: `28`
- `MINE_IMPLEMENTATION_PATTERN`: `15`
- `MINE_TEST_PATTERN`: `3`
- `NOT_RELEVANT`: `3`
- `REJECT`: `5`

## Enforcement

- `upstream_adoption_gate.json` is machine-authoritative for catalog completeness and subsystem review.
- A selected repository is not considered integrated until `upstream_usage.jsonl` records a concrete implemented usage state and valid implementation/test paths.
- Source adaptation remains prohibited unless an exact bounded source-incorporation review records revision, source path, project path, license/notice, hash, and tests.
- Rejected/not-relevant entries require a recorded rationale and cannot be activated without a new review.

## Implementation queue

- P0: worker/context/tool-gateway/evaluation/security candidates that materially affect the next major implementation areas.
- P1: verification, local-model, backup, cost, and browser/repository tooling.
- P2: architecture/implementation/test patterns that must be consulted before their owning subsystem advances.
- CLOSED: explicit rejections or no-core-role entries.

Machine-readable details: `catalog_dispositions.jsonl` and `adoption_queue.json`.
