# UPSTREAM-077 — openlit/openlit

- **Canonical URL:** `https://github.com/openlit/openlit`
- **Inspected revision:** `24224bdfad8628c639742e49fddc303675067416`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `Apache-2.0`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected OpenTelemetry-native agent and model instrumentation profile; telemetry ownership remains in Project Pipeline.

## Useful concepts

- OpenTelemetry-native AI instrumentation
- GPU monitoring
- evaluations and guardrails
- OTLP export

## Reviewed files and surfaces

- `README.md`
- `sdk`
- `backend`
- `LICENSE`

## Integration boundary

- Consume the internal telemetry contract as an optional deployment backend.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

OpenTelemetry-native integration aligns with backend portability and avoids proprietary instrumentation in domain code.

## Risk and operability review

- **Security:** Telemetry may contain sensitive prompts, outputs, hardware information, and credentials; require redaction and access controls.
- **Portability:** Self-hosting includes additional data services; agent SDKs are easier to trial than the complete platform.
- **Maintenance:** Pin SDK and backend versions and test OTLP compatibility.
- **Maturity:** `ACTIVE_EMERGING_PLATFORM`
- **Compatibility:** `DIRECT_DEPENDENCY_AGENT_OBSERVABILITY`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/openlit/openlit`
- `https://docs.openlit.io`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: OpenLIT is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
## Project Pipeline integration state

Project Pipeline now implements an optional OpenLIT initialization bridge over its existing OpenTelemetry boundary; missing installation remains an explicit unavailable state.
