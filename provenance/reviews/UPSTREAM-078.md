# UPSTREAM-078 — open-policy-agent/conftest

- **Canonical URL:** `https://github.com/open-policy-agent/conftest`
- **Inspected revision:** `c149d816bb161496cdb2402a720fa5e291236690`
- **Inspection state:** `FOCUSED_REVIEW_COMPLETE`
- **License:** `Apache-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected configuration and infrastructure policy test runner using the same Rego policy family as OPA.

## Useful concepts

- policy tests over structured configuration
- shared Rego rules
- CI preflight

## Reviewed files and surfaces

- `README.md`
- `policy examples`
- `LICENSE files`

## Integration boundary

- Invoke only after exact license confirmation; equivalent OPA evaluation may be used directly meanwhile.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Reusing policy language in runtime and CI reduces rule drift, but the CI tool is replaceable.

## Risk and operability review

- **Security:** Policy bundles and parsed untrusted configuration require sandbox and resource limits.
- **Portability:** Single binary is operationally simple.
- **Maintenance:** Repository metadata did not assert an SPDX license in the inspected snapshot.
- **Maturity:** `MATURE_FOCUSED_TOOL`
- **Compatibility:** `DIRECT_DEPENDENCY_POLICY_TESTING`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/open-policy-agent/conftest`
- `https://www.conftest.dev`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: Conftest is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
