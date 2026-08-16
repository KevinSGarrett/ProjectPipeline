# UPSTREAM-114 — winsw/winsw

- **Canonical URL:** `https://github.com/winsw/winsw`
- **Inspected revision:** `1d0ee4a91bad596d5e7e9c360f2b39ef54674674`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected Windows service wrapper for eligible long-running backend processes after installer, recovery, and rollback qualification.

## Useful concepts

- generic executable service wrapper
- service recovery
- logging and environment configuration

## Reviewed files and surfaces

- `README.md`
- `src`
- `samples`
- `LICENSE`

## Integration boundary

- Package a pinned binary and generated service XML after service lifecycle tests.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Keep supervision external and replaceable; service wrappers must not own application state.

## Risk and operability review

- **Security:** Service account privilege, executable paths, update provenance, and configuration ACLs are critical.
- **Portability:** Windows-only by design; other profiles use native process supervisors or containers.
- **Maintenance:** Qualify v3 behavior and preserve rollback/uninstall assets.
- **Maturity:** `MATURE_WINDOWS_UTILITY`
- **Compatibility:** `DIRECT_DEPENDENCY_WINDOWS_SERVICE_PROFILE`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/winsw/winsw`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: WinSW is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
