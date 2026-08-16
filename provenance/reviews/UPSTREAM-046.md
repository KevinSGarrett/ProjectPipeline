# UPSTREAM-046 — google/or-tools

- **Canonical URL:** `https://github.com/google/or-tools`
- **Inspected revision:** `98c165af62df62b3056c2ee0fca66b24e79097cb`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `Apache-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Optional bounded optimizer after deterministic eligibility, conflicts, authority, and resource admission are established.

## Useful concepts

- constraint programming
- assignment and scheduling optimization
- bounded solver limits

## Reviewed files and surfaces

- `README.md`
- `ortools/sat`
- `examples`
- `LICENSE`

## Integration boundary

- Implement only after a benchmark proves improvement over deterministic heuristics.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Optimization should operate on an already admissible set and return an explainable candidate schedule.

## Risk and operability review

- **Security:** Unbounded optimization can consume excessive CPU or memory; enforce time and resource limits.
- **Portability:** Python packages exist, but binary size and platform support must be qualified on Windows.
- **Maintenance:** Use the stable release channel and pin native package hashes.
- **Maturity:** `MATURE_PRODUCTION_LIBRARY`
- **Compatibility:** `DIRECT_DEPENDENCY_PROFILE_OPTIONAL_OPTIMIZER`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/google/or-tools`
- `https://developers.google.com/optimization/`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: OR-Tools is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
## Project Pipeline integration state

Project Pipeline now implements an optional OR-Tools CP-SAT safe-set optimizer; its result is always revalidated against internal conflict, capacity, and lane invariants.
