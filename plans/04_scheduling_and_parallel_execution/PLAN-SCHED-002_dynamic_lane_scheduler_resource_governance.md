# PLAN-SCHED-002 — Dynamic Lane Scheduler and Resource Governance

- **Plan ID:** `PLAN-SCHED-002`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus required implementation detail
- **Source basis:** `SRC-001:L000492-L000568`, `SRC-009:L000022-L000022`, `SRC-014:L000378-L000748`, `SRC-014:L000859-L000946`, `SRC-017:L000360-L000438`, `GOV-001:L000436-L000455`

## PLAN-SCHED-002:SEC-01 Authority and scheduling boundary

The Dynamic Lane Scheduler consumes only work already accepted by the Project Control Kernel. It is authoritative for bounded admission into concurrent execution subject to deterministic conflict, resource, lease, policy, and backpressure rules. It cannot make an ineligible task eligible, override dependency truth, alter completion authority, or bypass external-write policy. Optimization output is always revalidated before admission.

## PLAN-SCHED-002:SEC-02 Conflict graph

Every schedulable task declares conservative resource claims. The scheduler builds an undirected conflict graph whose edges represent mutually unsafe concurrent execution. Conflicts include overlapping exclusive file or directory paths, symbols or modules when known, schema or database migration ownership, infrastructure surfaces, API/configuration contracts, ports, environments, services, fixtures, GPUs, provider slots, and other shared resources. Path conflicts include ancestor/descendant overlap, not only exact string equality.

## PLAN-SCHED-002:SEC-03 Safe parallel-set calculation

The scheduler chooses a safe independent set from ready work rather than maximizing worker count. For bounded candidate sets it evaluates conflict-safe combinations deterministically and maximizes useful utility subject to resource capacity. Larger sets use a deterministic greedy fallback ordered by utility and stable task identity. Utility comes from the Build Sequencer's explainable priority output; the scheduler does not invent a second project-priority authority.

## PLAN-SCHED-002:SEC-04 Dynamic lanes and admission control

Lane count is recomputed from the current ready set, resource availability, active leases, runtime capacity, and backpressure state. Fixed lane counts are not a project invariant. Admission reserves capacity for the control plane, rejects impossible combinations, and never dispatches work whose required exclusive resource or bounded shared capacity cannot be acquired. Independent work may continue when unrelated work is blocked.

## PLAN-SCHED-002:SEC-05 Resource registry and capacity

The resource registry models resource type, stable resource key, total capacity, reserved capacity, machine scope, and observation provenance. Local observation may determine CPU, memory, disk, and process capacity with standard operating-system interfaces. GPU, port, environment, provider, credential, or service capacity is recorded only when explicitly configured or observed; the scheduler must not fabricate unavailable hardware. Capacity snapshots are machine-readable and reproducible from their inputs.

## PLAN-SCHED-002:SEC-06 Leases and fencing

Resource ownership uses bounded leases carrying lease identity, task, holder, resource claim, acquisition time, expiry, renewal state, and a monotonic fencing token. Multi-resource acquisition is atomic: partial bundles are rolled back if any claim cannot be admitted. Expired leases cease to authorize work. Renewal and release require the current holder and fencing token, so stale workers cannot reclaim or release a resource after a newer owner has acquired it.

## PLAN-SCHED-002:SEC-07 Workspace and high-contention resources

One executable work item maps to one isolated working context when repository mutation is involved. Repository Steward worktrees and ownership claims remain the source of Git isolation truth, while the scheduler consumes conservative path and semantic claims to avoid simultaneous edits to shared surfaces. Database migration sequences, infrastructure environments, schemas, ports, GPUs, and other high-contention resources receive explicit exclusive or capacity-bounded claims.

## PLAN-SCHED-002:SEC-08 Backpressure and brownout

Backpressure is a first-class scheduling input. Queue pressure, CPU, memory, disk, event lag, and active-capacity pressure produce deterministic operating modes: normal, congested, brownout, or halt-new-work. Congestion reduces admission. Brownout and halt-new-work stop optional new dispatch while preserving already admitted authoritative work. The scheduler protects control-plane reserve and never responds to overload by discarding canonical state.

## PLAN-SCHED-002:SEC-09 Persistence, CLI, and simulation

Scheduler plans, resource registries, leases, fencing counters, and simulation results are persisted through the existing migration and local-store framework. CLI operations expose read-only planning, resource/lease inspection, status, and scenario simulation. Acquire, renew, and release operations require explicit apply and approval flags. Simulations cover normal, congested, brownout, and halted admission without mutating external systems.

## PLAN-SCHED-002:SEC-10 Verification and remaining boundary

Verification covers resource-claim validation, path overlap, conflict construction, deterministic safe-set selection, capacity reserves, active-lease exclusion, atomic bundle acquisition, fencing-token enforcement, expiry/renewal/release, backpressure, migration application and rollback, CLI approval boundaries, simulation determinism, and repository self-audit. This implementation does not yet activate provider/model routing, monetary budget leases, distributed worker heartbeats, or a durable orchestration engine; those remain separate downstream capabilities.
