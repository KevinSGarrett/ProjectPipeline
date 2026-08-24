# Draft release factory

ProjectPipeline builds a **content-addressed release candidate** from one SHA/tree, binds SBOM/license/checksum/provenance, and stores the exact bytes as a **GitHub draft release**. Publication is blocked until the governed 4-hour, 24-hour, and 72-hour qualification sequence passes.

## Version authority

- Bundle/tag version is `config/version_compatibility.json` `platform_version`, which must match `pyproject.toml` and `src/project_pipeline/__init__.py`.
- Desktop/npm/Tauri/Cargo versions must match each other. They may differ from the Python platform version; that dual identity is recorded, not invented.
- Mixed-head artifacts are rejected.

## Dedup

- Native desktop compilation remains `C16-UX-01`. This factory **binds already-qualified** Windows executable/installer bytes.
- Local installer residue remains `C16-UX-05`. This factory acquires **remote draft bytes** by exact hash in a separate directory.

## Signing

If no authorized Authenticode identity is provisioned, the factory records `BLOCKED_EXTERNAL_SIGNING_IDENTITY_MISSING` and continues unsigned internal qualification. It does not treat missing signatures as a pass.

## GitHub

Create, upload, readback, unknown-outcome reconcile, and finalize are GitHub Steward operations. Finalization re-reads the campaign database at the GitHub Steward mutation boundary and requires a clean, attested 72-hour campaign whose SHA/tree exactly match the release candidate.
