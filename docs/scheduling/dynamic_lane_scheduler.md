# Dynamic Lane Scheduler

The Dynamic Lane Scheduler converts Project Control Kernel ready work into a bounded, conflict-safe concurrent admission plan. It never makes a task ready; it only decides whether already-ready work can execute concurrently under current resource and operating constraints.

## Inputs

The scheduler consumes a deterministic ready-work sequence, conservative task resource claims, the current resource registry, active leases, a requested lane ceiling, and current backpressure signals. Task utility is inherited from the Build Sequencer's explainable score so scheduling does not create a competing priority authority.

## Conflict model

Exclusive claims conflict when they address the same resource or overlapping path scopes. Shared capacity claims do not conflict with each other but must fit within the resource pool's available units after control-plane reserve and active leases. High-contention resources such as migration sequences, schemas, infrastructure environments, ports, GPUs, and explicit services are represented as semantic resource keys.

## Selection

For bounded candidate sets, Project Pipeline evaluates independent combinations deterministically and chooses the highest-utility feasible set. A deterministic greedy fallback is used when candidate count exceeds the bounded exact-search threshold. Stable task identity breaks ties.

## Backpressure

Normal operation admits the bounded feasible set. Congested operation reduces lane capacity. Brownout and halt-new-work modes admit no optional new work. Existing work is not cancelled by a planning decision.

## Truth boundary

The current implementation is locally and mock verified. It does not claim distributed-worker, GPU-provider, monetary-budget, or live external-system qualification. Those integrations remain separately governed.
