# UPSTREAM-050 — hatchet-dev/hatchet

- **Canonical URL:** `https://github.com/hatchet-dev/hatchet`
- **Inspected revision:** `4253c86ca3a763a6065b4134a6017a630b610061`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Initial durable execution backend behind DurableExecutionPort, selected by the latest source chronology.

## Useful concepts

- worker queues
- durable task execution
- rate and concurrency controls
- control-plane visibility

## Reviewed files and surfaces

- `README.md`
- `sdks/python`
- `pkg`
- `LICENSE`

## Integration boundary

- Mine operational and worker-control patterns; retain as a future WorkflowRuntime candidate.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

A separate control plane provides strong operational visibility but adds deployment and state-reconciliation burden.

## Risk and operability review

- **Security:** Control-plane credentials, worker registration, and tenant boundaries require independent threat review.
- **Portability:** Self-hosting is possible but introduces additional services beyond the local-first baseline.
- **Maintenance:** Active project; package and server compatibility must be tested together.
- **Maturity:** `ACTIVE_PRODUCTION_ORIENTED`
- **Compatibility:** `DIRECT_DEPENDENCY_INITIAL_DURABLE_BACKEND`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/hatchet-dev/hatchet`
- `https://docs.hatchet.run/`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: Hatchet is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
