# UPSTREAM-070 — networkx/networkx

- **Canonical URL:** `https://github.com/networkx/networkx`
- **Inspected revision:** `9266db885598a9d0b8f2d24ac6fef877e9137b96`
- **Inspection state:** `FOCUSED_REVIEW_COMPLETE`
- **License:** `BSD-3-Clause`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected deterministic graph-analysis library for dependency, conflict, resource, and critical-path calculations.

## Useful concepts

- directed graph algorithms
- cycle detection
- topological ordering
- path analysis

## Reviewed files and surfaces

- `README.rst`
- `networkx/algorithms`
- `LICENSE files`

## Integration boundary

- Compare with the internal graph model after exact package license and dependency review.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Commodity graph algorithms can be reused, but Project Pipeline graph semantics and validation remain internal.

## Risk and operability review

- **Security:** Algorithmic complexity and unbounded graph input can cause denial of service; enforce limits.
- **Portability:** Pure Python is attractive for local operation.
- **Maintenance:** Mature project, but current repository API license metadata was unasserted in the inspected snapshot.
- **Maturity:** `MATURE_WIDELY_USED`
- **Compatibility:** `DIRECT_DEPENDENCY_GRAPH_ANALYSIS`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/networkx/networkx`
- `https://networkx.org`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: NetworkX is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
## Project Pipeline integration state

NetworkX is an active runtime dependency in the control and scheduler graph paths.
