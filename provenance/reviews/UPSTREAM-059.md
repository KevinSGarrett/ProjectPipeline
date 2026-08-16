# UPSTREAM-059 — langfuse/langfuse

- **Canonical URL:** `https://github.com/langfuse/langfuse`
- **Inspected revision:** `ab58010c81339ffb3e19fc491d71733cf4f10f6a`
- **Inspection state:** `FOCUSED_REVIEW_COMPLETE`
- **License:** `MIT`
- **Disposition:** `EVALUATE_LATER`
- **Dependency activation eligible:** `false`
- **Source incorporation approved:** `false`

## Project Pipeline role

Alternative observability and evaluation platform retained for later comparison; OpenTelemetry remains the contract and OpenLIT is the initial agent instrumentation profile.

## Useful concepts

- LLM traces and metrics
- evaluation datasets
- prompt management
- OpenTelemetry integration

## Reviewed files and surfaces

- `README.md`
- `web`
- `packages`
- `license files`

## Integration boundary

- Consume Project Pipeline telemetry through OTLP only after license and data-handling review.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Keep telemetry semantics independent from the backend so an observability product remains replaceable.

## Risk and operability review

- **Security:** Prompts, outputs, user data, and evaluation sets may contain secrets or personal data.
- **Portability:** Self-hosting adds multiple services and storage dependencies.
- **Maintenance:** Large active platform with unasserted GitHub license metadata; inspect exact distribution terms before use.
- **Maturity:** `HIGH_ADOPTION_PLATFORM`
- **Compatibility:** `EVALUATED_ALTERNATIVE`

## License and provenance boundary

MIT-licensed core outside ee/, web/src/ee/, and worker/src/ee/; enterprise paths are excluded.

**Disposition rationale:** Reviewed and retained as a qualified alternative or later-profile candidate; it is not selected for initial activation.

**Dependency implications:** No initial activation; re-review only when a documented profile or measured need justifies it.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/langfuse/langfuse`
- `https://langfuse.com`
