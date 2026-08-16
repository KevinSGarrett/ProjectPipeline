# UPSTREAM-061 — max-sixty/worktrunk

- **Canonical URL:** `https://github.com/max-sixty/worktrunk`
- **Inspected revision:** `1e0ca1ce660421cb685b9c69ca421838100e2315`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT OR Apache-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected Git worktree lifecycle implementation behind RepositoryWorkspacePort and Repository Steward.

## Useful concepts

- worktree create, switch, status, merge, and cleanup
- parallel-agent workflow hooks
- per-worktree ports and cache-copy patterns

## Reviewed files and surfaces

- `README.md`
- `LICENSE-MIT`
- `LICENSE-APACHE`

## Integration boundary

- Invoke through Repository Steward with dry-run and path validation
- use native Git fallback when unavailable

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Commodity worktree ergonomics can be reused while assignment and merge authority remain internal.

## Risk and operability review

- **Security:** ['Hooks and subprocess arguments can execute arbitrary commands; disable untrusted configuration', 'destructive cleanup requires ownership checks']
- **Portability:** ['Windows installation and Linux/macOS support documented']
- **Maintenance:** ['Pin CLI version and verify behavior around data-preserving operations']
- **Maturity:** `Active rapidly evolving tool focused on parallel agent worktrees.`
- **Compatibility:** `DIRECT_DEPENDENCY_BEHIND_REPOSITORY_PORT`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `SRC-016:L001765-L001766`
- `SRC-016:L002181-L002191`
- `github:max-sixty/worktrunk@1e0ca1ce:README.md`
## Project Pipeline integration state

Project Pipeline now implements an approval-gated Worktrunk CLI bridge for JSON worktree listing and bounded create/remove operations using fixed argument vectors and no shell.
