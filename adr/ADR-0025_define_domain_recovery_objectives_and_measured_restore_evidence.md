# ADR-0025 — Define domain-specific recovery objectives and require measured restore evidence

- **Status:** ACCEPTED
- **Authority:** engineering decision grounded in canonical requirements and bounded upstream review
- **Source references:** `SRC-017:L000439-L000489`
- **Resolves:** `OPEN-DEC-0023`

## Context

Persistent domains have different business impact and therefore cannot share one arbitrary recovery objective. Objective values must be explicit enough to test and revise with measured evidence.

## Decision

Define recovery objectives per persistent domain in configuration and require measured isolated restore evidence before production-readiness claims. The configured values are engineering targets until real recovery exercises establish observed RPO/RTO.

## Alternatives considered

- One RPO/RTO for every domain
- No explicit recovery targets until production

## Consequences

- Makes recovery readiness measurable by business impact
- Targets remain provisional until real restore exercises establish observed performance

## Authority boundary

Project Pipeline retains deterministic project-state, recovery, security, budget, lease/fencing, and completion authority. Optional runtimes, backup tools, and cloud services provide bounded mechanics only. Live external qualification requires pinned provenance and environment-specific evidence.
