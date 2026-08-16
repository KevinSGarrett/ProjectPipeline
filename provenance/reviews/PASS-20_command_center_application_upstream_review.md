# Pass 20 Command Center Application Upstream-First Review

## Gate result

The Pass 20 Command Center application material-implementation gate is satisfied at the source/application boundary. The candidate set remains exactly the six Command Center candidates established in Pass 19: AG-UI, assistant-ui, CopilotKit, T3 Code, Tauri official plugins, and Mozzie. No upstream source is copied into Project Pipeline.

This pass distinguishes **source integration** from **external runtime qualification**. The React/Vite and Tauri source boundaries are implemented, but the execution environment cannot resolve npm packages from the registry and does not provide Rust/Cargo. Therefore no claim is made that a production React bundle, Tauri executable, MSI, or NSIS installer was built here.

## Dispositions

### UPSTREAM-003 — ag-ui-protocol/ag-ui — retain bounded protocol compatibility

- Keep the Pass 19 AG-UI compatibility adapter at the transport edge.
- `EventEnvelope`, Project Pipeline state, policy, evidence, completion, and typed controls remain authoritative.
- Pass 20 consumes the internal Command Center API contract; it does not add an external AG-UI SDK dependency.

### UPSTREAM-009 — assistant-ui/assistant-ui — pattern mining only

- Mine composable React interaction, streaming-status, retry, keyboard, and accessibility patterns.
- Do not activate it for Pass 20 because full Director Chat is deliberately a later pass and the current application does not need a chat framework to render canonical operational state.

### UPSTREAM-023 — CopilotKit/CopilotKit — pattern mining with authority boundary

- Mine human-in-the-loop and shared-state presentation concepts.
- Reject frontend-writable shared state as canonical Project Pipeline state.
- All operator mutations continue through authenticated typed commands, policy, idempotency, audit, and canonical transitions.

### UPSTREAM-084 — pingdotgg/t3code — compact control-surface reference

- Mine compact navigation, status hierarchy, and coding-agent operator UX patterns.
- No source or runtime dependency is incorporated.

### UPSTREAM-103 — tauri-apps/plugins-workspace — bounded source adapter implemented, runtime unqualified

- Implement the Tauri v2 shell source boundary and declare only the official notification capability used by the current desktop profile.
- Capability allowlist: `core:default` + `notification:default`; no shell, filesystem, opener, or generic HTTP plugin permission is granted.
- CSP restricts control transport to the loopback Project Pipeline API/WebSocket endpoint.
- The source adapter is implemented and contract-validated, but external dependency/runtime qualification remains **UNAVAILABLE_IN_EXECUTION_ENVIRONMENT** until Rust/Cargo and approved package resolution are available.
- Windows installer signing/updater qualification remains a required later release/deployment gate.

### UPSTREAM-110 — usemozzie/mozzie — archived reference only

- Retain local-first desktop workflow and parallel-work visualization lessons.
- Do not activate or copy source. Archive status makes it unsuitable as a new runtime dependency.

## Browser/accessibility evidence tool boundary

The existing reviewed Playwright browser-automation boundary is used for deterministic offline Chromium verification of the Pass 20 preview. No new axe-core or Lighthouse dependency is activated in this pass because the environment cannot resolve additional npm packages; semantic, keyboard, viewport, overflow, forced-color, reduced-motion, console-error, and interaction checks are performed directly through Playwright.

## Authority result

Pass 20 may implement and verify the Command Center application source because canonical authority remains in Project Pipeline. UI caches/projections are non-authoritative, authentication material is kept in memory, remote Jira/GitHub freshness is never fabricated, approval/recovery detail fails closed when a live provider is absent, and native capabilities remain least-privilege.
