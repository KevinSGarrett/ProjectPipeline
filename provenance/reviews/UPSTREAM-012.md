# UPSTREAM-012 — BerriAI/litellm

- **Canonical URL:** `https://github.com/BerriAI/litellm`
- **Inspected revision:** `f03df1bb42223ab8fa68033b01533295bf855188`
- **Inspection state:** `FOCUSED_REVIEW_COMPLETE`
- **License:** `MIT`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Replaceable multi-provider model gateway behind ProviderGateway; only MIT-licensed core paths are in scope and enterprise-only paths are excluded.

## Useful concepts

- provider normalization
- fallback and load balancing
- cost accounting
- guardrail hooks

## Reviewed files and surfaces

- `README.md`
- `LICENSE files`
- `provider adapters`

## Integration boundary

- Optional provider-gateway adapter only after license and stable-release review.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Normalize provider calls behind Project Pipeline contracts, but do not let a gateway own routing authority or budget truth.

## Risk and operability review

- **Security:** Gateway sees prompts, credentials, and outputs; requires strict redaction, tenant boundaries, and egress controls.
- **Portability:** Broad provider support is useful but behavior varies by provider and release.
- **Maintenance:** Large fast-moving repository with a nonstandard default branch; activate only a pinned released core package and exclude enterprise-only paths.
- **Maturity:** `HIGH_ADOPTION_COMPLEX_REPOSITORY`
- **Compatibility:** `DIRECT_DEPENDENCY_BEHIND_PROVIDER_PORT`

## License and provenance boundary

MIT-licensed core outside enterprise/; enterprise content is excluded and remains separately licensed.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/BerriAI/litellm`
- `https://docs.litellm.ai/docs/`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_ACTIVATION_BLOCKED`
- Disposition: `EVALUATE_LATER`
- Dependency activation eligible: `false`
- Source incorporation approved: `false`
- Rationale: The canonical architecture selects LiteLLM, but the inspected repository metadata reports an unasserted license and an internal-staging default branch. Preserve the target architecture behind a port while denying activation until explicit human legal and release-channel approval.
## Project Pipeline integration state

Stable release v1.96.2 and current root licensing were rechecked. Project Pipeline now implements an optional OpenAI-compatible LiteLLM proxy adapter while explicitly excluding enterprise/ paths.
