# PP-380 Cycle 6 Corrected Dispositions

- Source ledger: `evidence/pp380_cycle5_execution_dispositions.json`
- Source map: `evidence/pp380_source_reconciliation_map.json`
- Row count: `325`
- Prior equivalence claims evaluated: `64`
- True exact-content equivalence rows: `8`
- Divergent equivalence rows reclassified: `56`

## Action counts
- `COMMIT_UNIQUE_PP380_DELTA`: `188`
- `PRESERVE_OBSERVED_RUNTIME_EVIDENCE`: `58`
- `PRESERVE_OWNER_ATTESTATION_PENDING`: `15`
- `SUPERSEDED_BY_EXACT_PR_HEAD_AND_EQUIVALENCE`: `8`
- `THREE_WAY_RECONCILE_AFTER_PR44`: `29`
- `THREE_WAY_RECONCILE_AFTER_PR46`: `27`

## Generation proof
- Generator version: `pp380-generator-v2`
- Receipt kind: `content_addressed_source_bound_not_signed`
- Source map SHA-256: `f9055cdf3b9aaa30c089f5fb796449692784e314db04b52233d06c682cc9bcbc`
- Source ledger SHA-256: `64d416f63d2b6fd8bdaf2c6880eeb363342567dfcc8fc8b092ae3a8a3e59ae23`
- Rows SHA-256: `4077ef247fc40cab595ae8f42d6227038aa43b7094f753a144d2574693dc5277`
- Self-consistent hash SHA-256: `ef5f20a8244d1e1ac3b5f9eaf96e5e7480f959abb06871cce2084869442a5560`
- Content-addressed receipt SHA-256: `592393b9cdbe8646ef660c3866d15727f39ff916a9c08cd4b340557c449ce426`

The content-addressed receipt binds generator version, exact source-map bytes, exact source-ledger bytes, resolved Git object IDs, and the derived rows. It is not a cryptographic signature. A self-consistent hash of values already stored in this document is not an acceptance proof.
