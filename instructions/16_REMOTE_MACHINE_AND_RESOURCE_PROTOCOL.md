# Remote Machine and Resource Protocol

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-16` |
| Status | `ACTIVE` |
| Pack version | `1.2.0` |
| Primary domains | `remote_machines` |
| Governing entry point | `AGENTS.md` |

## Declared machines

The primary development laptop has an NVIDIA RTX 5060 and is a primary-control candidate only while it holds a valid fenced control lease. The secondary CPU machine is declared as `COMFY-V4-CPU-01`, with Chrome Remote Desktop operator name `FIVERR-AI-RUNNER`. Hardware beyond those declarations is unknown until discovered.

`policies/MACHINE_REGISTRY.json` is the machine-readable registry. Declared is not live-verified.

## Discovery before dispatch

Determine reachability, OS, CPU/RAM, tools, Python/runtime versions, Git identity, workspace, free disk, network policy, remote execution channel, active task, heartbeat, and lease state. Do not assume SSH, WinRM, PowerShell Remoting, Tailscale service, or GUI automation is configured.

Prefer secure scriptable channels: SSH, PowerShell Remoting, WinRM, Tailscale-reachable worker service, ProjectPipeline worker, or bounded job runner. Chrome Remote Desktop is an operator fallback, not the default automation API.

## Safe workspace model

Use an independent clone/worktree on each machine, explicit branch ownership, Git push/pull or content-addressed artifact transfer, and resource leases. Never allow both machines to edit the same network-shared mutable Git tree.

Record machine, workspace, branch, task, base SHA, resource claims, environment, expected artifacts, heartbeat, lease/fencing token, and return channel.

## Suitable CPU-worker tasks

Dispatch unit/integration tests, builds, static analysis, CPU-heavy deterministic evaluation, long-running jobs, benchmark execution, packaging, and other work that benefits from offload without GPU dependence. Do not dispatch solely to demonstrate machine use.

Consider transfer cost, environment parity, tool availability, data classification, reproducibility, conflict risk, and merge order.

## Result contract

The worker returns immutable logs/artifacts with digests, command/environment record, exit status, evidence identity, branch/SHA, changed files if any, and unresolved blockers. The primary control plane validates results before accepting canonical state.

## Worker loss

When heartbeat expires, fence the old lease, inspect remote branch/artifact state, reconcile uncertain effects, preserve available work, and only then reassign. A returning stale worker cannot publish using an expired token.

## Sensitive data and secrets

Transfer only the minimum permitted data. Secret and local-only data do not move to a worker without explicit policy and a scoped runtime lease. Do not store long-lived credentials on the worker for convenience.

## Recovery and fallback

If the remote channel fails, stop repeated connection attempts at policy limits, preserve the job record, continue locally or on another eligible worker, and provide an exact operator action if physical/GUI intervention is required. See `17` and `18`.
