# Command Center Tauri desktop shell

This directory defines the bounded Tauri v2 shell for the React Command Center.

## Security and authority boundaries

- Tauri is a packaging and OS-integration boundary, not a project-state authority.
- Authentication follows `ADR-0028`: local OS identity, one-time loopback handshake, ephemeral in-memory session.
- Only the official notification plugin is enabled in the initial capability allowlist.
- Filesystem, process shell, unrestricted opener, clipboard, global shortcut, updater, and arbitrary HTTP plugins are not granted by default.
- The web client uses the authenticated Project Pipeline Command Center API for state and controls.
- The content-security policy allows only local application resources plus loopback Command Center HTTP/WebSocket traffic.

## Reproducible build

- Toolchain: `rust-toolchain.toml` (Rust 1.97.1)
- Locks: `Cargo.lock` and `apps/command_center/package-lock.json`
- Hosted dual-lane compare: `.github/workflows/desktop-windows.yml`
- Normalization allowlist: `config/desktop_nondeterminism_schema.json`

## Runtime qualification

Run `runbooks/command_center_windows_qualification.md`. Offline Chromium preview evidence does not certify the native PE, installer, window, or recovery journey.
