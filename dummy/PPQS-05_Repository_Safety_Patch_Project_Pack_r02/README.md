# PPQS-05 — Repository Safety Patch Project Pack

This is the **visible candidate pack** for the `EXISTING_PROJECT` `SMALL` PPQS benchmark. It contains the complete legitimate starting state: business/product source material, intake request, seed Jira and GitHub mirrors, seed repositories or exact acquisition manifest where applicable, fixtures, visible tests, mocks, constraints, environment contract, fault-overlay catalog, and candidate-output location.

## Start

1. Read `BENCHMARK_BRIEF.md`, `INPUT_MANIFEST.json`, and `constraints/benchmark_boundary.json`.
2. Acquire the exact pinned upstream source using `python common/tooling/acquire_repository.py --manifest acquisition/source.json --destination <target> --allow-network`.

3. Reset into an isolated workspace using the shared public reset tool.
4. Run ProjectPipeline intake in dry-run/local mode before authorizing any external mutation.
5. Let ProjectPipeline independently create normalized requirements, plans, Jira work, implementation, tests, evidence, release artifacts, and final completion audit.

## Critical isolation rule

The private Oracle Pack is not a development dependency. Do not mount, index, search for, infer, or access it. The evaluator tests outcomes after the run from a separate trust boundary.

## Seed summary

- Project profiles: GENERIC, DOCUMENTATION
- Assigned overlays: GITHUB_JIRA_UNKNOWN_WRITE_OUTCOME, NETWORK_LOSS
- Repository shape: ONE_MATURE_REPOSITORY
- External mutation: denied by default
