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
- Source ledger SHA-256: `1031df5316e123497384e5f0516f7620ebeb181746b7ca19137ba9fd9373ad07`
- Rows SHA-256: `4077ef247fc40cab595ae8f42d6227038aa43b7094f753a144d2574693dc5277`
- Self-consistent hash SHA-256: `b5b691a0b42eb32f072fedc0c7dfef2b4d325f34dbb37c4ee6c663e5f4872d3e`
- Content-addressed receipt SHA-256: `68848add7fad0fc053f11732b33ed3c7aa59b19294c8766708f4a4db8bcaf36c`

The content-addressed receipt binds generator version, exact source-map bytes, exact source-ledger bytes, resolved Git object IDs, and the derived rows. It is not a cryptographic signature. A self-consistent hash of values already stored in this document is not an acceptance proof.
