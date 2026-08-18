---
name: remote-cpu-worker
description: Discover and dispatch bounded ProjectPipeline work to COMFY-V4-CPU-01 safely.
---

# Remote CPU Worker

1. Read instructions `10`, `16`, and `17` plus `policies/MACHINE_REGISTRY.json`.
2. Discover and verify reachability, OS, CPU/RAM, tools, workspace, disk, channel, heartbeat, and lease.
3. Choose a CPU-suitable task only when transfer, reproducibility, isolation, and conflict economics are favorable.
4. Create an independent clone/worktree and record task, branch, base SHA, resource claims, expected artifacts, and return channel.
5. Transfer minimum permitted data; secrets require scoped runtime authority.
6. Require structured result, logs, environment, digests, exit status, evidence, and branch/SHA.
7. Validate returned work before canonical acceptance.
8. On worker loss, fence, inspect, reconcile, preserve, then reassign or record a typed external precondition with no operator work assignment.
