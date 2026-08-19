# Evidence definitions and observation receipts

Source-controlled `evidence/EVIDENCE_LEDGER.jsonl` rows are **definitions**. They name a stable evidence ID, claim, criteria, requirements, artifact, digest, method, environment, and policy. They do not prove the current integrated commit.

A separate immutable **observation receipt** records an actual execution against an exact subject SHA and tree. Observations live in the governed runtime store outside the subject Git tree:

- `.local/state/evidence/observations.sqlite3`
- `.local/state/evidence/observations/OBSV-*.json`
- `PPDB-0024` when the project-state database is used

Reconciliation consumes a definition plus a valid current observation. A stale, wrong-tree, wrong-environment, mock-only, failed, missing-artifact, missing-test-catalog, or unverified observation fails closed.

Shared evidence is not a single fingerprint. Each observation records `requirement_scope_fingerprints` for every linked requirement and `test_outcomes` for every listed test. Reconciliation matches the evaluated requirement's current acceptance-scope fingerprint and requires that requirement's cataloged tests to be `PASS`. An unrun node/UI test or a source change in one requirement cannot fail-close unrelated siblings that share the same evidence ID.

## Self-reference rule

Writing the current SHA or tree into a source-controlled evidence row cannot converge. The commit that stores the binding changes the subject it names. Observations therefore stay outside the acceptance-bearing tree. Metadata-only reconciliation (allowlisted `implementation_state` and generated Jira/index paths) may inherit an observation after a post-merge refresh when the acceptance-scope fingerprint is unchanged. Changing an acceptance-bearing source file invalidates inherited observations.

A branch head SHA is not the integrated SHA. Squash merges require an explicit post-merge exact-head receipt. Tree equivalence may support refresh only when proven.

Historical observations are immutable. Newer receipts supersede them; they do not rewrite prior results.

## CLI

```text
python -m project_pipeline evidence list --root .
python -m project_pipeline evidence get --root . --evidence-id EVID-000001
python -m project_pipeline evidence status --root .
python -m project_pipeline evidence generate --root . --evidence-id EVID-000001
python -m project_pipeline evidence verify --root . --observation-id OBSV-...
python -m project_pipeline evidence refresh --root .
python -m project_pipeline evidence reconcile --root .
```
