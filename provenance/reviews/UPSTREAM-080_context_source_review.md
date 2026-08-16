# UPSTREAM-080 — Serena Context Pattern Review

- Repository: `oraios/serena`
- Inspected revision: `93ec043105f5ee4f5ff64ea0158041500d2cdc65`
- License: MIT
- Decision: `MINE_IMPLEMENTATION_PATTERN`; no authority or direct runtime dependency is granted.

## Source-level findings

`src/serena/tools/symbol_tools.py` demonstrates a useful context-minimization discipline: obtain a compact top-level symbol overview before requesting bodies, search by semantic symbol/name path, bound match counts and answer size, and progressively shorten results when a response is too large. Reference queries also return narrow source context rather than whole files.

Project Pipeline adopts this **symbol-first, progressively bounded retrieval pattern** in its Context Broker/Compiler policy: requested keys first, no unrequested repository dump, required material before optional material, explicit context-size limits, and omission/freshness accounting. Project Pipeline does not copy Serena's editing authority or use it as a source-of-truth engine.

## Evidence sources

- https://github.com/oraios/serena/tree/93ec043105f5ee4f5ff64ea0158041500d2cdc65
- https://github.com/oraios/serena/blob/93ec043105f5ee4f5ff64ea0158041500d2cdc65/src/serena/tools/symbol_tools.py
