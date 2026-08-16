# UPSTREAM-079 — open-policy-agent/opa

- **Canonical URL:** `https://github.com/open-policy-agent/opa`
- **Inspected revision:** `16b5a013726fff3c2197f98ac4afcd6d2218588a`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `Apache-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected declarative runtime policy decision engine behind PolicyPort.

## Useful concepts

- policy as code
- structured input and decisions
- bundle versioning
- decision logs

## Reviewed files and surfaces

- `README.md`
- `rego`
- `topdown`
- `LICENSE`

## Integration boundary

- Call through PolicyPort and retain policy version, input hash, outcome, and reasons.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

The policy engine decides according to a bundle; application enforcement points remain responsible for actually preventing actions.

## Risk and operability review

- **Security:** Policy distribution, decision logs, built-ins, and bundle signatures require strict governance.
- **Portability:** Standalone binary and server modes support local and cloud profiles.
- **Maintenance:** Pin a release and test Rego compatibility before bundle upgrades.
- **Maturity:** `MATURE_CLOUD_NATIVE_POLICY_ENGINE`
- **Compatibility:** `DIRECT_DEPENDENCY_BEHIND_POLICY_PORT`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/open-policy-agent/opa`
- `https://www.openpolicyagent.org`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: OPA is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
