# Compilation Model

An intake compilation combines observed repository facts with explicit caller intent. It produces a strict, immutable model containing:

- project identity and intake mode;
- repository identity and discovery summary;
- discovered authority surfaces;
- detected project profiles and activated policy implications;
- deterministic repository-map entries;
- structured gap records with severity, category, rationale, affected paths, and suggested remediation;
- source-authority and operating-constraint declarations;
- a semantic fingerprint and stable compilation identifier.

## Greenfield and adoption modes

`NEW_PROJECT` treats a sparse project root as an intentional starting point and recommends only the minimum reviewable bootstrap authorities.

`EXISTING_PROJECT` treats all pre-existing files as potentially human-authored authority. It records observed state, identifies gaps, and refuses destructive cleanup or overwrite behavior. Existing-project intake does not grant autonomous execution authority.

## Profiles

Profile detection is deterministic and evidence-based. Profiles can describe language, application shape, repository scale, data/ML characteristics, deployment surfaces, and existing governance. Profiles alter policy recommendations and validation scope; they do not rewrite repository structure merely because a size threshold was crossed.

## Persistence and authority

Compilations can be persisted through the transactional repository port. The local SQLite profile is executable and migration-backed. PostgreSQL remains the selected production authority boundary, but live PostgreSQL verification is still externally blocked.

A persisted compilation is an observed and derived projection. It does not silently replace human-authored plans, Jira records, requirements, architecture decisions, or project-control state.
