# API Reference

The stable operator-facing HTTP boundary is the FastAPI Command Center application constructed by `project_pipeline.command_center.api.create_command_center_app`. It exposes health, authenticated capabilities/status/application projections, Operator Inbox operations, notification dispatch, timeline replay, SSE/WebSocket events, Director context/chat, incident verification, and typed command execution.

Canonical project state is not owned by HTTP, SSE, WebSocket, AG-UI compatibility events, React, Tauri, WinSW, or Docker. Mutations must return through typed Project Pipeline command/control boundaries with authentication, authorization, idempotency, policy, fencing/recovery, and audit semantics.

The package CLI is exposed through `project-pipeline` / `python -m project_pipeline`. `python -m project_pipeline --help` is the executable command inventory. Repository validation is `python -m project_pipeline validate --root .`.

Target-specific API deployment must configure authentication secrets through the secret-reference/runtime boundary and must not embed tokens in committed configuration.
