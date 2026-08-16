# Command Center Tauri desktop shell

This directory defines the bounded Tauri v2 shell for the React Command Center.

## Security and authority boundaries

- Tauri is a packaging and OS-integration boundary, not a project-state authority.
- Only the official notification plugin is enabled in the initial capability allowlist.
- Filesystem, process shell, unrestricted opener, clipboard, global shortcut, updater, and arbitrary HTTP plugins are not granted by default.
- The web client continues to use the authenticated Project Pipeline Command Center API for state and controls.
- The content-security policy allows only local application resources plus loopback Command Center HTTP/WebSocket traffic.

## Runtime qualification status

The source boundary is implemented, but this execution environment has no Rust/Cargo toolchain and cannot produce or certify an MSI/NSIS build. A real Windows qualification must install the current supported Tauri/Rust prerequisites, install the pinned JavaScript dependency set, build the web application, run `tauri build`, validate signatures/installer behavior, and execute the browser/desktop acceptance journeys. The lack of that external qualification is intentionally not hidden by the offline Chromium UI evidence.
