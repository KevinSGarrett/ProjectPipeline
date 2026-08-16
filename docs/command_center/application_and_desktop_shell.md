# Command Center application and desktop shell

Pass 20 adds the operator-facing application layer over the authenticated Pass 19 Command Center API.

## Application boundary

The React client is a projection and control surface. It does not own project state, completion state, approvals, budgets, incidents, provider truth, Jira truth, GitHub truth, or evidence. Read models come from the canonical API; every mutation is a typed `CommandEnvelope` returned through the existing authorization, policy, idempotency, audit, persistence, and recovery path.

The application includes professional navigation and surfaces for project readiness, graph traceability, live work, layered health/risk, budgets, provider/agent performance, context health, recovery, approvals, Jira/GitHub reconciliation, and evidence drill-down. The project graph links requirements, Jira work, and evidence using authoritative IDs rather than browser-generated identities.

## Authentication and client state

Bearer credentials are held in memory by the application session abstraction. The source deliberately does not persist auth tokens in `localStorage`, `sessionStorage`, IndexedDB, or a Tauri store. Reconnection may rebuild views from the API and replayable event cursor; a browser cache is not a recovery authority.

## Desktop shell

The Tauri v2 shell is intentionally narrow. It packages the same web application and activates only the official notification plugin in the initial capability set. Filesystem, process shell, arbitrary opener, unrestricted HTTP, clipboard, updater, and global-shortcut permissions are not granted by default. The CSP allows local application assets and loopback Command Center HTTP/WebSocket traffic only.

Tauri itself is not a control-plane shortcut. Native notifications may draw operator attention, but clicking or responding to a notification must re-enter the authenticated application workflow before any project mutation can occur.

## Responsive and accessibility behavior

The layout has desktop, tablet, and narrow-mobile breakpoints, keyboard-visible focus, a skip link, semantic landmarks, labelled controls, accessible status text, reduced-motion handling, and a forced-colors treatment. Pass 20 runs the repository-local preview through real Chromium/Playwright at 1440×900, 1024×768, and 390×844 plus a forced-colors rendering.

The preview is intentionally dependency-free and contains representative non-authoritative records so browser layout can be verified when package-registry access is unavailable. It does **not** certify the React/Vite package build or the Tauri native build. Those toolchain gaps are preserved as external qualification work rather than converted into a false pass.

## Director scope

The application reserves the existing Director API boundary but does not claim the complete conversational incident-management experience in Pass 20. Full Director Chat and richer incident/operator interaction remain later-scheduled work.
