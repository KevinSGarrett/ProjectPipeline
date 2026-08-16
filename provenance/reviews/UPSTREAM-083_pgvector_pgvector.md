# UPSTREAM-083 — pgvector/pgvector

- **Canonical URL:** `https://github.com/pgvector/pgvector`
- **Inspected revision:** `1a79ebccc2ab3131eb6fcb97aae1188606c410a3`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `PostgreSQL`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected PostgreSQL extension for the default semantic retrieval profile.

## Useful concepts

- exact and approximate vector search in PostgreSQL
- HNSW and IVFFlat indexes
- ACID and relational filtering with vector retrieval

## Reviewed files and surfaces

- `README.md`
- `LICENSE`

## Integration boundary

- Store embeddings with source, model, chunk, and freshness metadata
- use exact retrieval and deterministic filters before similarity ranking

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Colocating vectors with canonical metadata avoids a mandatory extra service.

## Risk and operability review

- **Security:** ['Restrict extension installation and index-resource use', 'treat retrieved text as untrusted context']
- **Portability:** ['Docker is the preferred Windows development route', 'native Windows build is documented']
- **Maintenance:** ['Version extension with database migrations and backup tests']
- **Maturity:** `Widely used mature PostgreSQL extension.`
- **Compatibility:** `DIRECT_DEPENDENCY_SEMANTIC_PROFILE`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `SRC-011:L000601-L000652`
- `github:pgvector/pgvector@1a79ebcc:README.md`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: pgvector is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
