# UPSTREAM-103 — tauri-apps/plugins-workspace

- **Canonical URL:** `https://github.com/tauri-apps/plugins-workspace`
- **Inspected revision:** `db9c5998feff9384f9cbbefcbe0d45937c00a1fc`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT OR Apache-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected official native capability plugins for the optional Tauri Windows shell, subject to least-privilege scope review.

## Useful concepts

- capability-scoped native plugins
- desktop notifications
- updater and process integration

## Reviewed files and surfaces

- `README.md`
- `plugins`
- `permissions`
- `LICENSE`

## Integration boundary

- Use the smallest official plugin set with explicit capability allowlists.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Native desktop capabilities should be isolated from the web client and granted per capability.

## Risk and operability review

- **Security:** Plugins expand native attack surface; require allowlists, code signing, updater verification, and no shell access by default.
- **Portability:** Tauri targets multiple desktop platforms; Windows is the initial qualified profile.
- **Maintenance:** Track the v2 branch and plugin/core compatibility matrix.
- **Maturity:** `ACTIVE_OFFICIAL_ECOSYSTEM`
- **Compatibility:** `DIRECT_DEPENDENCY_DESKTOP_PROFILE`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/tauri-apps/plugins-workspace`
- `https://tauri.app`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: Tauri official plugins is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
