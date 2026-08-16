# UPSTREAM-086 — pydantic/pydantic-ai

- **Canonical URL:** `https://github.com/pydantic/pydantic-ai`
- **Inspected revision:** `372240802a1ae8f47da628bef88362e24d9074a7`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected typed advisory-agent framework behind provider-neutral internal contracts.

## Useful concepts

- typed structured outputs
- provider abstraction
- tool calling
- dependency injection and evaluation

## Reviewed files and surfaces

- `README.md`
- `pydantic_ai`
- `tests`
- `LICENSE`

## Integration boundary

- Implement a provider adapter without exposing framework types to control-domain modules.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Typed outputs improve validation, but agent frameworks remain advisory and disposable.

## Risk and operability review

- **Security:** Tool use and model content remain untrusted; enforce policy outside framework callbacks.
- **Portability:** Python package fits the core, while provider behavior remains external.
- **Maintenance:** Fast-moving framework; pin and qualify model/provider combinations.
- **Maturity:** `ACTIVE_EMERGING_FRAMEWORK`
- **Compatibility:** `DIRECT_DEPENDENCY_ADVISORY_AGENT_LAYER`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/pydantic/pydantic-ai`
- `https://ai.pydantic.dev/`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: Pydantic AI is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
## Project Pipeline integration state

Pydantic AI v2.31.0 was rechecked. Project Pipeline now implements an optional typed advisory-agent adapter and a bounded provider-compatibility data contract with MIT provenance.
