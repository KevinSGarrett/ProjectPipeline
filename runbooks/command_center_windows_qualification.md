# Command Center Windows qualification runbook

## Purpose

Qualify the native Windows Command Center desktop and authenticated loopback service on a real supported Windows environment. Browser-only screenshots do not qualify `REQ-UX-0004`.

## Authority

- `ADR-0028` / `OPEN-DEC-0018`: local OS identity plus ephemeral session auth; loopback-only by default.
- Desktop compilation and developer-candidate identity are owned by this runbook (`C16-UX-01` through `C16-UX-05`).
- Cross-ecosystem bundling of an already-qualified desktop artifact is a later release-factory concern.

## Preconditions

1. Use a clean checkout of the exact candidate SHA/tree and verify `FILE_MANIFEST.sha256`.
2. Pin toolchains from `rust-toolchain.toml` (Rust 1.97.1), `apps/command_center/package-lock.json`, and `apps/desktop_shell/src-tauri/Cargo.lock`.
3. Prefer the hosted Windows workflow `.github/workflows/desktop-windows.yml` when local disk is constrained. Two fresh jobs must compare normalized PE/installer payloads.
4. Download hosted artifacts to the authorized Windows machine and verify SHA-256 before execution.
5. Keep the backend on loopback. Do not persist tokens.

## Qualification

1. `npm --prefix apps/command_center ci`
2. `npm --prefix apps/command_center test`
3. `npm --prefix apps/command_center run build`
4. `cargo fmt --check`, `cargo clippy --locked -- -D warnings`, and `cargo test --locked` in `apps/desktop_shell/src-tauri`
5. `npm --prefix apps/command_center run tauri:build -- -- --locked` or consume the hosted PE, MSI, and NSIS artifacts
6. Record raw hashes, normalized hashes, every allowlisted stripped field from `config/desktop_nondeterminism_schema.json`, and the comparison algorithm
7. Launch the real desktop binary; verify the native process and window; hydrate live repository/Control/Jira/GitHub state through authenticated loopback APIs
8. Exercise service-not-running bootstrap, service loss, websocket reconnect, process restart, stale token, and expired session
9. Resolve the upgrade predecessor through GitHub release readback. If none exists, record `NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR` and exercise clean install/repair/rollback/uninstall only
10. Scan logs, argv, crash data, installed config, browser storage, and handshake files for secret residue

## Failure rule

Any missing lockfile, unallowlisted binary difference, non-loopback bind, token persistence, unsigned claim without an authorized signing identity, or skipped native-window proof keeps Windows desktop runtime qualification **NOT VERIFIED**. `REQ-UX-0004` remains `PARTIALLY_IMPLEMENTED` until the exact-main integrated journey succeeds.
