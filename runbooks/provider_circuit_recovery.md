# Provider Circuit Recovery

1. Inspect provider runtime state and the current circuit record.
2. Distinguish transient unavailability from disabled, authentication-failed, or budget-exhausted state.
3. Do not reset an open circuit merely to force routing.
4. After the configured recovery interval, permit only bounded half-open probes.
5. Record successful recovery or reopen the circuit on probe failure.
6. Requalify a changed adapter/model version before restoring high-risk eligibility.
7. Continue unaffected work through qualified fallback providers when policy permits.
