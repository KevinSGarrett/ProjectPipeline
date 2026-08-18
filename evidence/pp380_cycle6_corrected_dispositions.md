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
- Rows SHA-256: `2b5bd6219699e9e7dff65ee21aa99bf71b75f9138cadffa870cfda35ed899f6e`
- Self-consistent hash SHA-256: `c93e622fd459c81f32be2ad38ffc34f6ab827eacc52b68bf90b43bfa8b47a48d`
- Content-addressed receipt SHA-256: `949d0180a7b47641bdc2b82d14c4f2458996e91df7d852c0da7024b8ce3c8aca`

The content-addressed receipt binds generator version, exact source-map bytes, exact source-ledger bytes, resolved Git object IDs, and the derived rows. It is not a cryptographic signature. A self-consistent hash of values already stored in this document is not an acceptance proof.
