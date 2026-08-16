# ADR-0023 — Keep control local-primary and use AWS only as an optional cloud spine

- **Status:** ACCEPTED
- **Authority:** engineering decision grounded in canonical requirements and bounded upstream review
- **Source references:** `SRC-012:L000001-L000217`, `SRC-012:L000380-L000495`
- **Resolves:** `OPEN-DEC-0019`

## Context

Canonical sources call for a local-primary architecture with an optional AWS support plane and explicitly warn against moving the main orchestrator to cloud by default.

## Decision

Keep the deterministic control plane local-primary. Use AWS only as an optional cloud spine for witness, durable events, recovery storage, observability, budget controls, ingress/watchdog, and explicitly activated bounded recovery or burst capacity.

## Alternatives considered

- Move primary director to AWS
- Always-running EC2 control plane
- No cloud spine

## Consequences

- Retains local autonomy and low steady cloud cost
- Requires explicit fencing/reconciliation for optional DR activation

## Authority boundary

Project Pipeline retains deterministic project-state, recovery, security, budget, lease/fencing, and completion authority. Optional runtimes, backup tools, and cloud services provide bounded mechanics only. Live external qualification requires pinned provenance and environment-specific evidence.
