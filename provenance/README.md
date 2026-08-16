# Provenance

This directory records supplied sources, governing artifacts, and upstream decisions without copying the authoritative raw knowledge corpus into the permanent repository.

- `source_registry.json` and `source_pack_reference.json` preserve canonical source identities and duplicate relationships.
- `upstream_registry.json` catalogs all supplied repositories and records revision-pinned reviews, dispositions, and activation eligibility.
- `review_program.json` records completed and queued review cohorts.
- `reviews/` contains evidence-bearing repository evaluations.
- `license_policy.json` separates dependency activation from source-incorporation approval.

Unknown or unreviewed repositories remain non-activatable and non-incorporable. No upstream source code has been copied into Project Pipeline.
