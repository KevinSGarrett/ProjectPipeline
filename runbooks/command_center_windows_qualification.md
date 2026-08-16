# Command Center Windows qualification runbook

## Purpose

Qualify the Pass 20 React/Tauri source boundary on a real supported Windows environment without changing Project Pipeline authority semantics.

## Preconditions

1. Use a clean checkout of the exact release candidate and verify `FILE_MANIFEST.sha256`.
2. Install a supported Node.js version, current stable Rust/Cargo toolchain, Tauri v2 Windows prerequisites, and WebView2 prerequisites according to official Tauri documentation.
3. Install JavaScript dependencies from the approved lockfile or approved dependency resolution after vulnerability/license review. Do not use a surprise `latest` upgrade during release qualification.
4. Keep the backend on loopback or an explicitly approved authenticated reverse proxy.

## Qualification

1. Run Command Center Node model tests.
2. Build the React/Vite application and retain build logs plus dependency/SBOM evidence.
3. Run the existing Chromium responsive/accessibility verification against the built application.
4. Run `tauri build` and capture exact Rust, Cargo, Tauri, plugin, WebView2, Windows, and compiler versions.
5. Install the MSI/NSIS package on a clean Windows test account.
6. Verify startup, shutdown, resize/minimum size, keyboard navigation, screen-reader accessible names, notification permission and delivery, loopback API reconnect, offline/degraded messaging, and no unauthorized network origins.
7. Verify safe controls still produce typed API commands and cannot mutate state when unauthenticated, unauthorized, stale, or replayed.
8. Verify installer uninstall/rollback and preservation rules for user-local non-secret preferences.
9. Record hashes, screenshots, logs, test results, installer identity/signature evidence, and any exceptions in the evidence ledger.

## Failure rule

Any missing toolchain evidence, permission expansion, network-origin expansion, token persistence, unsigned/untrusted installer result, or authority bypass keeps Windows desktop runtime qualification **NOT VERIFIED**.
