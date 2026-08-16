# UPSTREAM-035 — FiloSottile/age

- **Canonical URL:** `https://github.com/FiloSottile/age`
- **Inspected revision:** `706dfc1e799a03443ae46023502bd88d4e9e324f`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `BSD-3-Clause`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Recipient and key mechanism used by SOPS for local encrypted configuration.

## Useful concepts

- small explicit recipients
- composable encryption
- simple key format

## Reviewed files and surfaces

- `README.md`
- `cmd`
- `LICENSE`

## Integration boundary

- Use age recipients for SOPS-encrypted configuration and documented key rotation.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Simple recipient files reduce configuration complexity and help keep plaintext outside the repository.

## Risk and operability review

- **Security:** Private identities must never enter source, logs, artifacts, prompts, or context packs.
- **Portability:** Portable binaries are available, but Windows installation and key permissions require verification.
- **Maintenance:** Focused tool with a stable conceptual surface; pin binary provenance.
- **Maturity:** `MATURE_FOCUSED_TOOL`
- **Compatibility:** `DIRECT_DEPENDENCY_SECRET_ENCRYPTION`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/FiloSottile/age`
- `https://age-encryption.org`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: age is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
