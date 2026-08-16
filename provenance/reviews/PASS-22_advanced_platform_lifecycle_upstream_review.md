# Pass 22 Advanced Platform Lifecycle upstream review

Reviewed for the Pass 22 platform-lifecycle boundary on 2026-08-15 UTC.

## Cohort and disposition

| Upstream | Pass 22 disposition | Boundary |
|---|---|---|
| `UPSTREAM-028` devcontainers/spec | mine architecture patterns | reproducible environment metadata only; Windows-first/local profiles remain valid |
| `UPSTREAM-036` OpenSpec | mine implementation patterns | specification/change lifecycle ideas only; Project Pipeline requirements/plans/Jira remain canonical |
| `UPSTREAM-042` github/spec-kit | mine implementation patterns | specification-to-implementation workflow patterns only |
| `UPSTREAM-055` mise | mine implementation patterns | tool/runtime version declaration and qualification patterns only; not a bootstrap dependency |
| `UPSTREAM-061` worktrunk | retain existing bounded external CLI adapter | worktree/repository workspace lifecycle only; Repository Steward remains authoritative |
| `UPSTREAM-089` Renovate | **blocked from activation** | AGPL-3.0-only remains prohibited by current Project Pipeline license policy |
| `UPSTREAM-090` restic | reuse existing optional backup adapter | archive/closure backup plan only; Project Pipeline owns retention and deletion decisions |
| `UPSTREAM-106` DVC | mine architecture patterns | data-version/provenance concepts only; content-addressed Project Pipeline artifacts remain canonical |

## Current upstream evidence reviewed

- Development Containers specification remains a public portability specification intended to make development environments reproducible; repository licensing remains path/mixed-license scoped in the Project Pipeline catalog.
- OpenSpec currently publishes an MIT license, resolving the prior `LICENSE_FILE_PRESENT_UNRESOLVED` catalog state.
- GitHub Spec Kit currently publishes an MIT license and remains an actively developed specification-driven development toolkit.
- mise currently publishes an MIT license and continues to provide tool/environment/task version management concepts.
- Worktrunk remains actively maintained and dual-licensed `MIT OR Apache-2.0`.
- Renovate remains an active dependency-update project under `AGPL-3.0`; activation is prohibited by `provenance/license_policy.json`.
- restic remains an actively maintained BSD-2-Clause backup program; its already-implemented Project Pipeline adapter is reusable for verified archive/restore planning.
- DVC remains an actively maintained Apache-2.0 data/model versioning project; only architecture patterns are mined in Pass 22.

## Authority decision

Project Pipeline is canonical for project identity, repository membership, portfolio priority, environment ownership, test-data classification, contract compatibility, lifecycle transitions, retention state, closure readiness, version qualification, platform-release eligibility, and adoption maturity. Upstreams may supply declarative formats, optional adapters, or implementation patterns only.

No upstream is authorized to delete artifacts, close a project, promote a platform release, rewrite project contracts, choose global resource priority, or mutate an adopted project by itself.

## Destructive-action boundary

Pass 22 implements deterministic **plans and state machines** for cleanup, archive, retirement, and closure. Destructive deletion, credential revocation, cloud teardown, or external repository mutation requires a separately authorized typed action plus verification evidence. A retention expiry by itself is never deletion authority.

## License/source-incorporation boundary

No upstream source is copied or substantially adapted in this pass. Renovate remains blocked. The other candidates are used only through existing adapters or independently implemented patterns, so source-incorporation approval is not required.
