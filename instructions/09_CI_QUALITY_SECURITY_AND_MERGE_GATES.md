# CI, Quality, Security, and Merge Gates

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-09` |
| Status | `ACTIVE` |
| Pack version | `1.0.0` |
| Primary domains | `ci`, `merge_gate`, `security` |
| Governing entry point | `AGENTS.md` |

## Risk-based assurance

The baseline CI remains conventional and reproducible: schema/dependency checks, Ruff, mypy, pytest/coverage, repository validation, build, and dependency audit. Add checks because a risk requires them, not to display tool count. `policies/CI_RISK_MATRIX.json` is the machine-readable tier map.

## Change classes

- Fast path: typo, simple documentation, nonfunctional comments, deterministic generated refresh. Run links, secrets, instruction checks when governed files change, and targeted repository checks.
- Tier A: normal code. Run repository contract, schemas/dependencies, lint/format, applicable typing, targeted and related tests, coverage regression, and build when affected.
- Tier B: dependency/supply chain. Add dependency review, vulnerability audit, license/provenance, lock consistency, and policy checks.
- Tier C: security/control plane. Add CodeQL, security/adversarial/fault tests, authority checks, independent review, and rollback material.
- Tier D: UI. Add browser, accessibility, and visual evidence where behavior is visual.
- Tier E: release/post-merge/scheduled. Add broad end-to-end, applicable PPQS, performance/fault/recovery, artifacts, SBOM, integrity, provenance, and install verification.
- Tier I: instructions or policy. Treat as high-impact self-modification and run validator, cold start, scenarios A–L, secret scan, authority consistency, and independent review.

## Coverage

Coverage is evidence about exercised code, not a target to game. Preserve the project baseline, avoid unexplained global regression, and strongly cover changed deterministic business logic, failure paths, acceptance behavior, and high-risk controls. Do not add overlapping coverage services without a demonstrated gap.

## Test integrity

Do not delete, weaken, skip, or alter a test solely to make it green. Trace an apparently incorrect test to its requirement and acceptance, determine whether test or implementation is wrong, change the correct artifact, and preserve rationale. Never optimize PPQS scores by weakening visible acceptance.

## Security and supply chain

- all third-party GitHub Actions use immutable full commit SHAs with release comments;
- workflow permissions are least privilege;
- secret scanning and push protection should be enabled in repository settings when available;
- CodeQL covers applicable source changes;
- Dependabot proposes controlled dependency and action updates;
- runtime dependencies receive vulnerability audit and provenance/license review;
- release artifacts include SBOM, hashes, and provenance as required;
- unreviewed third-party actions, install scripts, binaries, and containers are not trusted.

## AI review

AI review is advisory or independently required according to risk. It focuses on authority, traceability, mutation safety, idempotency, recovery, concurrency, evidence, secrets, and state semantics. It never replaces tests, analysis, protection, security scanning, evidence, or Completion Gate.

Limit review loops: validate each finding, correct material findings, dismiss invalid findings with rationale, and rerun applicable checks. Do not chase inconsistent cosmetic preferences.

## Merge protection target

Once `main` exists, configure the strongest sensible low-cost rules:

- pull request required before integration;
- direct implementation pushes blocked;
- selected current-head status checks required;
- force pushes and branch deletion blocked;
- material conversations resolved;
- required independent approval for high-risk areas;
- merge queue only if actual concurrency justifies it and merge-group CI is configured.

Source-controlled workflow files do not prove live settings. Verify through GitHub state and record activation evidence.

## Local parity

Required CI checks have documented local commands in `README.md`, `Makefile`, and the instruction manifest. A merge-critical check should not exist only as unexplained hosted behavior when local reproduction is feasible.
