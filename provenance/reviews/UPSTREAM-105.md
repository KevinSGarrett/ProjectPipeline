# UPSTREAM-105 — testcontainers/testcontainers-python

- **Canonical URL:** `https://github.com/testcontainers/testcontainers-python`
- **Inspected revision:** `f7d3887fe7c78e0b3a8b6eae82e105a4d3e0bca0`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `Apache-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected disposable real-service test harness for PostgreSQL and integration dependencies.

## Useful concepts

- ephemeral dependency containers
- isolated integration fixtures
- automatic lifecycle management

## Reviewed files and surfaces

- `README.md`
- `testcontainers`
- `tests`
- `LICENSE`

## Integration boundary

- Provision PostgreSQL for persistence, DBOS, migration, and recovery tests.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Real dependency tests catch behavior that mocks cannot, but must remain isolated and cleaned up.

## Risk and operability review

- **Security:** Container images are supply-chain inputs; pin image digests and restrict Docker privileges.
- **Portability:** Requires Docker or a compatible engine; tests must skip explicitly when unavailable.
- **Maintenance:** Pin library and image versions and verify Windows/WSL2 behavior.
- **Maturity:** `MATURE_TEST_LIBRARY`
- **Compatibility:** `DIRECT_DEPENDENCY_INTEGRATION_TESTING`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/testcontainers/testcontainers-python`
- `https://testcontainers-python.readthedocs.io/`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: Testcontainers Python is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
