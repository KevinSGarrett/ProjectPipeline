# Resilience gaps

Isolated provider-removal simulation reports coverage, schedule, cost, and blocked work
without mutating live paid services. Uncommitted work can be preserved and restored with
digest proof. Restore apply is allowlist-isolated: it uses `RestoreTargetPolicy` plus the
same destination guards as preservation, and it refuses drive roots, UNC shares, `.git`,
protected prefixes, secret paths, traversal, and digest mismatch. GPU-dependent work
enters WAITING_RESOURCES while CPU-safe independent lanes continue and recheck remains
machine-owned.

On Windows, the host-safety gate is also a live capacity gate for sustained
campaign work. It rejects low available physical memory or low commit headroom
before a build or duration stage begins, alongside its volume and recent
storage-fault checks. The check is read-only: it records compact capacity
counters and never changes paging, storage, firmware, or power settings.
