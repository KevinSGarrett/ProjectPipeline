# Draft release factory

ProjectPipeline builds a **content-addressed release candidate** from one SHA/tree, binds SBOM/license/checksum/provenance, and stores the exact bytes as a **GitHub draft release**. Publication is blocked until the governed 4-hour, 24-hour, and 72-hour qualification sequence passes.

For a public-source checkout, the factory derives a deterministic license inventory from the
license declarations bound in `requirements/environment.lock.json`. The inventory is emitted
alongside the bundle, hashed in the supply binding, declared in provenance, and re-verified before
it can be accepted; absent or altered license metadata fails closed.

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

Create, upload, readback, unknown-outcome reconcile, and finalize are GitHub Steward operations. Every asset name is normalized once before the local manifest, upload, GitHub readback, and remote-byte acquisition; this accounts for GitHub's whitespace-to-dot filename rewrite without weakening exact asset-set or checksum checks.

An uncertain create, upload, or finalization response is reconciled by remote readback before a fresh write is considered. Finalization re-reads the immutable campaign database immediately before the GitHub mutation and requires a clean, attested 72-hour campaign whose SHA/tree and event hashes exactly match the release candidate.

After finalization, assets are downloaded into an immutable candidate-scoped remote-byte directory. Its manifest, publication receipt, and on-disk file set must agree exactly; stale extras and alternate archives are rejected. Wheel and source-distribution checks run in separate clean environments without inherited project import paths, install their declared runtime dependencies, and run the CLI doctor against source extracted from the acquired archive.
