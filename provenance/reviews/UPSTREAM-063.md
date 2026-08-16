# UPSTREAM-063 — microsoft/playwright

- **Canonical URL:** `https://github.com/microsoft/playwright`
- **Inspected revision:** `a0af4bf3ae711b062fbc31d1655f76af870817c1`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `Apache-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Authoritative cross-browser functional, accessibility, visual, and evidence-capture test implementation.

## Useful concepts

- single API across browser engines
- tracing and screenshots
- isolated browser contexts
- reliable locators

## Reviewed files and surfaces

- `README.md`
- `packages/playwright`
- `tests`
- `LICENSE`

## Integration boundary

- Use a pinned browser matrix and retain traces, screenshots, and reports as evidence artifacts.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Browser evidence should be deterministic, accessibility-aware, and mapped to acceptance criteria.

## Risk and operability review

- **Security:** Downloaded browsers and test pages are executable supply-chain inputs; pin versions and isolate untrusted pages.
- **Portability:** Works across major desktop platforms; CI caches and browser installation require management.
- **Maintenance:** Pin Playwright and browser revisions together.
- **Maturity:** `MATURE_WIDELY_ADOPTED`
- **Compatibility:** `DIRECT_DEPENDENCY_ACCEPTANCE_TESTING`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/microsoft/playwright`
- `https://playwright.dev`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: Playwright is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
