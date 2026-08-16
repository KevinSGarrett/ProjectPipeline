# UPSTREAM-039 — getsops/sops

- **Canonical URL:** `https://github.com/getsops/sops`
- **Inspected revision:** `30332a959e3d987f622702519f6b52d8ff81e1dc`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MPL-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected structured encrypted-configuration tool with age recipients and optional cloud KMS profiles.

## Useful concepts

- encrypted YAML/JSON values
- multiple key providers
- repository-safe encrypted configuration

## Reviewed files and surfaces

- `README.rst`
- `cmd`
- `LICENSE`

## Integration boundary

- Invoke the SOPS binary through a narrow secret-materialization adapter.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Encrypted configuration can remain reviewable while plaintext is materialized only at runtime.

## Risk and operability review

- **Security:** Decrypted bytes, temporary files, command lines, and environment variables require strict handling and cleanup.
- **Portability:** Supports local and cloud key providers; Windows packaging and editor workflows need tests.
- **Maintenance:** Pin a released binary and preserve MPL notices; do not copy MPL source into proprietary modules.
- **Maturity:** `MATURE_WIDELY_USED`
- **Compatibility:** `DIRECT_DEPENDENCY_ENCRYPTED_CONFIGURATION`

## License and provenance boundary

MPL-2.0 dependency use; modifications and distribution require file-level notice/compliance review.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/getsops/sops`
- `https://getsops.io`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: SOPS is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
