# Upstream Usage Report

This report describes actual integration rather than catalog presence.

## Concrete integration now present

- `UPSTREAM-070` NetworkX — active runtime graph dependency.
- `UPSTREAM-046` OR-Tools — optional CP-SAT scheduling optimizer with Project Pipeline result revalidation.
- `UPSTREAM-061` Worktrunk — optional approval-gated worktree CLI adapter.
- `UPSTREAM-086` Pydantic AI — optional typed advisory-agent adapter plus a bounded provider-compatibility data adaptation.
- `UPSTREAM-012` LiteLLM — optional stable OpenAI-compatible proxy adapter; enterprise-licensed paths excluded.
- `UPSTREAM-029` Docker MCP Gateway — optional secure-default gateway adapter plus a bounded security-default data adaptation.
- `UPSTREAM-077` OpenLIT — optional OpenTelemetry-native AI instrumentation bridge.

Machine-readable state is authoritative in `upstream_usage.jsonl`, `upstream_registry.json`, and `source_incorporation_reviews/`.

## Remaining convergence work

Other selected repositories remain explicitly `SELECTED_NOT_ACTIVATED` until a concrete subsystem integration path exists. Catalog entries not yet deeply reviewed remain research candidates rather than implied dependencies. Future subsystem implementation is gated on relevant upstream review so mature commodity capabilities are not silently rebuilt without evaluating the supplied catalog first.
