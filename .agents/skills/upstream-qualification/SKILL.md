---
name: upstream-qualification
description: Qualify an upstream repository, dependency, pattern, or source adaptation through ProjectPipeline provenance gates.
---

# Upstream Qualification

1. Read instruction `14` and the existing upstream registry/adoption records.
2. Verify canonical URL, exact revision, license, notices, intended use, and prohibited subtrees.
3. Inspect source safely without executing scripts, hooks, binaries, builds, or containers.
4. Assess security, maintenance, compatibility, Windows/offline behavior, egress, footprint, and removal path.
5. Prefer existing implementation, standard library, supported dependency, adapter, then pattern mining.
6. Use bounded source adaptation only with explicit gate, provenance, notices, internal ownership, and tests.
7. Update dependency lock, SBOM/provenance expectations, documentation, and rollback in one cohesive change.
