# UPSTREAM-104 — temporalio/temporal

- **Canonical URL:** `https://github.com/temporalio/temporal`
- **Inspected revision:** `55cf6be564be2eb39e23fd6fa28a7ca6e59dcfa0`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT`
- **Disposition:** `MINE_ARCHITECTURE`
- **Dependency activation eligible:** `false`
- **Source incorporation approved:** `false`

## Project Pipeline role

Architecture and scale fallback reference for durable workflow execution; not approved as the initial dependency.

## Useful concepts

- event-history durable workflows
- separate frontend, history, matching, and worker services
- retry and recovery semantics

## Reviewed files and surfaces

- `README.md`
- `service`
- `common`
- `LICENSE`

## Integration boundary

- Retain a WorkflowRuntime compatibility target and migration test plan.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Strong durability and scale come with a separately operated cluster and strict deterministic workflow constraints.

## Risk and operability review

- **Security:** Namespace, worker, network, encryption, and visibility data boundaries require dedicated operations.
- **Portability:** Self-hosted and managed modes exist, but local deployment is heavier than the selected baseline.
- **Maintenance:** Mature platform with SDK/server compatibility and operational upgrade requirements.
- **Maturity:** `MATURE_PRODUCTION_PLATFORM`
- **Compatibility:** `ARCHITECTURE_AND_FALLBACK_REFERENCE`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Retained as a revision-pinned architecture and fallback reference. It is not selected for initial dependency activation.

**Dependency implications:** No initial activation; retain compatibility requirements and benchmark evidence for future reconsideration.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/temporalio/temporal`
- `https://docs.temporal.io`

## Project Pipeline disposition after source chronology review

- Source strategy: `QUALIFIED_FALLBACK_OR_LATER_PROFILE`
- Disposition: `EVALUATE_LATER`
- Dependency activation eligible: `false`
- Source incorporation approved: `false`
- Rationale: Reviewed and retained behind an internal port for a measured future trigger; it is not selected for initial activation and source incorporation is not approved.
