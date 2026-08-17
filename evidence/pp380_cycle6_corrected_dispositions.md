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
- Source map SHA-256: `abcdd71f9a64421a8411edaae06b6a4134885023fddc3079af78043cbf7a049d`
- Source ledger SHA-256: `64d416f63d2b6fd8bdaf2c6880eeb363342567dfcc8fc8b092ae3a8a3e59ae23`
- Rows SHA-256: `4077ef247fc40cab595ae8f42d6227038aa43b7094f753a144d2574693dc5277`
- Self-consistent hash SHA-256: `7f0e107d6ccc17371c523c6bee7629453d482953c24cef214156ba776d5d4679`
- Content-addressed receipt SHA-256: `641b2f6245518b7b7fbad55933d8a5995517bdbe2e14fa489b92f6d9dff4b9ae`

The content-addressed receipt binds generator version, exact source-map bytes, exact source-ledger bytes, resolved Git object IDs, and the derived rows. It is not a cryptographic signature. A self-consistent hash of values already stored in this document is not an acceptance proof.
