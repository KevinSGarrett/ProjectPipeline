# Resource Leases and Fencing

Project Pipeline uses bounded resource leases to prevent two workers from acting as simultaneous owners of an exclusive resource or from exceeding a bounded shared capacity.

Each lease records the task, holder, normalized resource claim, acquisition time, expiry, and a monotonically increasing fencing token. The fencing token is part of the authority check for renewal and release. A stale worker holding an older token is rejected after ownership has advanced.

Multi-resource task admission is atomic. If one claim cannot be acquired, no lease from the requested bundle remains committed. This prevents half-admitted tasks whose CPU slot was reserved but whose file, schema, port, GPU, or environment claim was denied.

Expired leases do not count as active ownership. Renewal extends only a currently active lease with the expected holder and token. Release is idempotent for the active owner but does not allow stale-token release.

Local resource pools may be observed for CPU, memory, disk, and process capacity. Resources that cannot be safely observed, including GPUs in environments without a qualified probe, are not invented and must be registered explicitly before they can be admitted.
