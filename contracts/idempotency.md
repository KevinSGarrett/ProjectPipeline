
# Idempotency Contract

A mutating operation has a stable idempotency identity scoped to actor, target, operation, and project. Repeated submission returns the recorded result when the original outcome is known. Unknown outcomes enter reconciliation and are not blindly replayed.
