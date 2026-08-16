# Upstream Adoption Gate

Project Pipeline treats the supplied upstream repository catalog as an implementation input. The gate prevents two opposite errors: blindly adding dependencies because they appear in the catalog, and silently rebuilding mature capabilities without reviewing cataloged alternatives.

The authoritative files are:

- `provenance/upstream_registry.json` — catalog identity, review depth, terminal disposition, license, and provenance.
- `provenance/catalog_dispositions.jsonl` — streaming terminal disposition ledger for all catalog entries.
- `provenance/upstream_usage.jsonl` — actual integration state; selection is not use.
- `provenance/upstream_adoption_gate.json` — subsystem-to-candidate review gate.
- `provenance/adoption_queue.json` — prioritized future integration/qualification work.
- `provenance/source_incorporation_reviews/` — exact bounded source-adaptation approvals.

## Required behavior

Before materially implementing a subsystem, inspect its candidate set in `upstream_adoption_gate.json`. Direct dependency use, external CLI adaptation, component adaptation, architecture mining, implementation/test-pattern mining, rejection, and non-relevance are all valid outcomes when evidence supports them.

A selected upstream is never considered integrated until `upstream_usage.jsonl` records an implemented usage state and every integration path exists. A repository with unresolved licensing cannot be activation eligible or source-incorporable. Adapted source/data requires the separate bounded-incorporation record, immutable revision, notice, hash, and tests.

`python scripts/validate_repository.py --root .` enforces these invariants. They are project governance, not an optional review checklist.
