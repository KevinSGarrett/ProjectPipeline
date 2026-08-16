# UPSTREAM-003 — ag-ui-protocol/ag-ui

- **Canonical URL:** `https://github.com/ag-ui-protocol/ag-ui`
- **Inspected revision:** `b70b564fc99504bf57a1d82feab714d67f85a563`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Optional AG-UI compatibility adapter for Director Chat and operator event streams; Project Pipeline retains the authoritative internal event model.

## Useful concepts

- versioned agent/user events
- streaming state updates
- frontend-agent separation

## Reviewed files and surfaces

- `README.md`
- `docs`
- `LICENSE`

## Integration boundary

- Implement a compatibility adapter from internal realtime events to AG-UI events.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Keep the internal event model authoritative and version the compatibility edge independently.

## Risk and operability review

- **Security:** Streaming events can expose prompts, tool arguments, or secrets unless fields are classified and redacted.
- **Portability:** Protocol use is portable; framework-specific frontend helpers must remain optional.
- **Maintenance:** Young protocol with active change; pin a compatibility version and retain contract tests.
- **Maturity:** `ACTIVE_EMERGING`
- **Compatibility:** `DIRECT_DEPENDENCY_COMPATIBILITY_ADAPTER`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/ag-ui-protocol/ag-ui`
- `https://ag-ui.com`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: AG-UI is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
