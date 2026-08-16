# Pass 19 Command Center Upstream-First Review

## Gate result

The Pass 19 material-implementation gate is satisfied. The reviewed candidate list exactly matches the Command Center adoption gate: AG-UI, assistant-ui, CopilotKit, T3 Code, Tauri official plugins, and Mozzie. No upstream source is copied into Project Pipeline.

## Dispositions

### UPSTREAM-003 — ag-ui-protocol/ag-ui — integrate bounded protocol adapter

- Current upstream evidence: `https://github.com/ag-ui-protocol/ag-ui` and official AG-UI documentation.
- License: MIT (previous deep review remains controlling).
- Pass 19 use: implement a Project Pipeline-owned compatibility adapter for AG-UI lifecycle/text/state/custom event families.
- Authority rule: `EventEnvelope` and Project Pipeline canonical state remain authoritative. AG-UI is a wire compatibility edge, not a state owner.
- Security rule: no private reasoning/chain-of-thought events; payload classification/redaction remains Project Pipeline policy.
- Maintenance rule: protocol compatibility is tested locally and may be versioned independently. No external SDK package is required by the Pass 19 backend.

### UPSTREAM-009 — assistant-ui/assistant-ui — mine frontend patterns, activation deferred

- Current upstream evidence: `https://github.com/assistant-ui/assistant-ui`.
- License: MIT.
- Useful patterns: composable production React chat primitives, streaming/retry UX, attachments, keyboard/accessibility behavior.
- Pass 19 decision: no backend dependency. Reserve it for later Director Chat client qualification after the API/realtime contract is stable.

### UPSTREAM-023 — CopilotKit/CopilotKit — mine HITL/shared-state patterns with authority rejection

- Current upstream evidence: `https://github.com/CopilotKit/CopilotKit`.
- License: MIT.
- Useful patterns: generative UI, human-in-the-loop interaction, agent/user shared-state presentation.
- Pass 19 boundary: frontend-writable shared state is never canonical Project Pipeline state. Mutations must be typed commands re-entering authorization/policy/audit.

### UPSTREAM-084 — pingdotgg/t3code — mine compact control-surface patterns

- Current upstream evidence: `https://github.com/pingdotgg/t3code`.
- License: MIT.
- Useful patterns: compact coding-agent control surfaces, session switching, status hierarchy, operator navigation.
- Pass 19 decision: reference patterns only; no runtime dependency or source adaptation.

### UPSTREAM-103 — tauri-apps/plugins-workspace — selected, intentionally deferred

- Existing deep review remains valid for the selected Windows desktop boundary.
- Pass 19 is backend/realtime; desktop native capability activation is therefore intentionally deferred.
- Later activation requires the smallest capability allowlist, pinned versions, Windows compatibility tests, code-signing/update verification, SBOM/notices, and rollback evidence.

### UPSTREAM-110 — usemozzie/mozzie — architecture mining only

- Current upstream evidence: `https://github.com/usemozzie/mozzie`; the repository is archived.
- License: MIT.
- Useful patterns: local-first desktop workflow, parallel work visualization, dependency/review UX.
- Pass 19 decision: no dependency activation. Archive status makes it a reference only.

## Resulting implementation boundary

Pass 19 may implement the Command Center backend after this review because the upstream-first gate is now explicit and bounded: Project Pipeline owns canonical state, action authority, replay cursors, inbox semantics, security, and persistence; AG-UI is implemented only as a compatibility transport adapter; frontend and desktop dependencies remain deferred to their own qualification pass.
