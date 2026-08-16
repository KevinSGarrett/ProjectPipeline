# Upstream integration runtime

Project Pipeline treats the supplied upstream catalog as an implementation resource, not a bibliography. The permanent Upstream Adoption Gate decides which candidates each subsystem must consider; `upstream_usage.jsonl` records actual use; and `p0_convergence.json` records closure of the highest-priority implementation queue.

## Integration classes

- **Runtime dependency:** imported and used directly by Project Pipeline.
- **Optional adapter:** code exists and is contract-tested, but the optional upstream package/service may not be installed or live-qualified.
- **External CLI adapter:** a fixed-argv, no-shell boundary exists for a qualified upstream executable. Project Pipeline does not auto-install an unpinned latest version.
- **Bounded source adaptation:** permitted only through the source-incorporation approval contract with immutable revision, license, notice, hash, and tests.
- **Pattern/test mining:** upstream influences independently implemented behavior without being represented as a dependency.

## P0 integrations

The P0 convergence set includes SWE-ReX, Repomix, official GitHub and Atlassian MCP servers, Codex, Gemini CLI, Promptfoo, Inspect AI, Gitleaks, OSV-Scanner, Cosign, and Zizmor. Each has a concrete Project Pipeline adapter/profile and contract tests. External installation, credentials, network access, provider spend, remote write permission, and live verification remain distinct activation concerns.

## Safety invariants

1. No subprocess adapter uses `shell=True`.
2. Worker writes require an approved Project Pipeline ActionIntent.
3. Network-enabled execution is denied unless explicitly allowed by the caller.
4. Codex dangerous bypass flags and Gemini yolo mode are forbidden.
5. Repomix security checks are not disabled.
6. Promptfoo sharing is disabled by the adapter.
7. OSV automated remediation is not exposed.
8. Cosign integration is verification-only and requires digest-addressed artifacts.
9. Zizmor defaults to offline strict collection.
10. MCP profiles store secret references, never credential values, and write operations remain owned by the relevant steward.

## Qualification

An implemented adapter is not automatically live verified. Before an upstream runtime becomes operational in a target environment, qualify the exact installed version/digest, license/notices, dependency vulnerability state, Windows compatibility where applicable, configuration, policy, credentials, rollback/removal path, and representative integration behavior.
