# Project Pipeline Command Center

React/Vite application source for the Project Pipeline operator Command Center.

## Authority boundary

- The application is a projection and control client. Rendered/browser state is never canonical.
- Read state comes from the authenticated Pass 19 Command Center API.
- Mutating controls submit typed `CommandEnvelope` documents through the existing authorization, policy, idempotency, audit, and recovery path.
- Bearer credentials are held only in an in-memory session abstraction. The app does not persist credentials to localStorage, IndexedDB, or the Tauri store.
- The offline preview is deterministic verification evidence only; it is not a live-system simulator and its example records must never be mistaken for canonical project state.

## Local development

The source expects React 19, Vite, and the Tauri v2 CLI. Dependency installation is intentionally not performed by repository code. In a qualified online development environment:

```bash
npm install
npm run dev
```

The Python backend should be served separately on `127.0.0.1:8765`; Vite proxies `/api` only during development. A production web deployment must use the same origin or an explicitly approved reverse proxy.

## Verification

- `npm test` runs dependency-free Node tests for the application model and typed-control construction.
- `scripts/verify_command_center_ui.py` renders the repository-local offline preview in real Chromium across desktop, tablet, and mobile viewports and records screenshots/accessibility evidence.
- A React/Vite package build and a native Tauri/Windows build remain external-toolchain qualifications. Their absence must be represented explicitly; the offline preview does not certify those build chains.
