# ADR-0027 — Keep Project-Native Locks Canonical with Optional mise and Dev Container Profiles

- **Status:** ACCEPTED
- **Authority:** engineering decision grounded in lifecycle/environment requirements and Pass 22 upstream review
- **Source references:** `SRC-009:L000012-L000012`, `SRC-011:L000912-L000943`, `SRC-017:L000597-L000670`, `SRC-017:L001002-L001063`
- **Resolves:** `OPEN-DEC-0027`

## Context

Project Pipeline needs reproducible language/tool environments across Windows-first local operation, CI, offline/degraded profiles, and optional containerized profiles. The environment contract cannot depend on one external environment manager becoming canonical.

## Decision

1. Project-native declarations and observed-environment locks remain canonical for required runtime/tool versions and compatibility state.
2. `mise` is an optional convenience/qualification adapter for developer tool-version activation where installed; Project Pipeline remains operable without it.
3. Dev Container metadata is an optional reproducibility profile for projects that choose containerized development. It is not mandatory for Windows-first/local-core operation.
4. New tool/runtime versions enter Project Pipeline qualification state before high-risk use. Availability from mise, a package manager, or a container image does not equal qualification.
5. Every project records platform/schema/adapter/policy/profile compatibility and surfaces unsupported combinations before promotion.

## Alternatives considered

- Make mise mandatory for all local/runtime version management
- Require Dev Containers as the canonical development environment
- Allow each project to choose unmanaged tool versions without a platform compatibility record

## Consequences

- Offline and Windows-first bootstrap remains independently operable.
- Teams can use mise or Dev Containers without transferring lifecycle authority to those tools.
- Reproducibility evidence can be compared across native and container profiles.
- External tool installation and activation remain separately permissioned operations.
