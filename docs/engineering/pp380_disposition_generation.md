# PP-380 Canonical Disposition Generation

The generator derives every row and action from versioned inputs plus explicit
fetched Git refs. It does not accept an already-corrected ledger as the
authoritative source.

## Versioned inputs

- `evidence/pp380_cycle5_execution_dispositions.json`
- `evidence/pp380_source_reconciliation_map.json`
- provenance: `evidence/pp380_source_reconciliation_map.provenance.json`

## Bounded Git ref preparation

In a clean single-branch clone, fetch the exact commits before generation:

```powershell
git fetch origin 2a82fc53f6422fd13aaf308f7024bf6850f49b01:refs/pp380/pr44
git fetch origin 626a365fad876e3e834830f208e9d05092899fd9:refs/pp380/pr46
git fetch origin 9c7abd5fb03bd778a8949f99bcb7c78b76ed21e9:refs/pp380/unique
```

If those objects are already present, the raw SHAs may be passed directly.

## Exact generator invocation

From the repository root, with `PYTHONPATH=src`:

```powershell
$env:PYTHONPATH = 'src'
& python scripts\generate_pp380_corrected_dispositions.py `
  --repo-root . `
  --source-ledger evidence/pp380_cycle5_execution_dispositions.json `
  --source-map evidence/pp380_source_reconciliation_map.json `
  --pr44-ref 2a82fc53f6422fd13aaf308f7024bf6850f49b01 `
  --pr46-ref 626a365fad876e3e834830f208e9d05092899fd9 `
  --pp380-ref 9c7abd5fb03bd778a8949f99bcb7c78b76ed21e9 `
  --output-json evidence/pp380_cycle6_corrected_dispositions.json `
  --output-md evidence/pp380_cycle6_corrected_dispositions.md
```

Re-running the same command on an unchanged tree must produce byte-identical
JSON and Markdown.

## Receipt semantics

- `self_consistent_hash_sha256` hashes values already stored in the document.
  An attacker who edits rows can recompute it. It is not acceptance proof.
- `content_addressed_receipt_sha256` binds generator version, the exact source
  map bytes, the exact source ledger bytes, resolved Git object IDs, and the
  derived rows. Independent verification re-hashes those sources. This receipt
  is content-addressed and is not a cryptographic signature.
