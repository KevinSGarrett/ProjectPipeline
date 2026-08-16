# ADR-0022 — Use a provider-neutral local model gateway with Ollama, llama.cpp, and optional llama-swap

- **Status:** ACCEPTED
- **Authority:** engineering decision grounded in canonical requirements and bounded upstream review
- **Source references:** `SRC-013:L001055-L001117`, `SRC-016:L001691-L001832`
- **Resolves:** `OPEN-DEC-0016`

## Context

The platform requires local/offline AI assistance without allowing a model runtime to become deterministic control authority. Multiple local runtime candidates already exist in the upstream catalog and must remain replaceable.

## Decision

Use a provider-neutral local model gateway. Ollama is the initial local-service candidate, llama.cpp is a direct-serving fallback, and llama-swap is an optional multi-model/hot-swap layer. No runtime or model is production-qualified until pinned and profile-verified.

## Alternatives considered

- Ollama only
- llama.cpp only
- llama-swap as mandatory front door

## Consequences

- Preserves replaceability and offline operation
- Requires per-runtime qualification and endpoint hardening

## Authority boundary

Project Pipeline retains deterministic project-state, recovery, security, budget, lease/fencing, and completion authority. Optional runtimes, backup tools, and cloud services provide bounded mechanics only. Live external qualification requires pinned provenance and environment-specific evidence.
