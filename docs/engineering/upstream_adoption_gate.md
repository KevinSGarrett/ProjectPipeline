# Upstream Adoption Gate

Project Pipeline treats the supplied upstream repository catalog as an implementation input. The gate prevents two opposite errors: blindly adding dependencies because they appear in the catalog, and silently rebuilding mature capabilities without reviewing cataloged alternatives.

The authoritative files are:

- A private maintainer registry records catalog identity, review depth, terminal disposition, license, and provenance.
- A private disposition ledger records every catalog decision and actual integration state; selection is not use.
- A private subsystem-to-candidate review gate and adaptation record bind approved source reuse to the exact upstream revision, license, and behavioral tests.

## Required behavior

Before materially implementing a subsystem, inspect its candidate set in `upstream_adoption_gate.json`. Direct dependency use, external CLI adaptation, component adaptation, architecture mining, implementation/test-pattern mining, rejection, and non-relevance are all valid outcomes when evidence supports them.

A selected upstream is never considered integrated until `upstream_usage.jsonl` records an implemented usage state and every integration path exists. A repository with unresolved licensing cannot be activation eligible or source-incorporable. Adapted source/data requires the separate bounded-incorporation record, immutable revision, notice, hash, and tests.

`python scripts/validate_repository.py --root .` enforces these invariants. They are project governance, not an optional review checklist.
