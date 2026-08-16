# Platform Upgrade Qualification Runbook

1. Detect the new platform/tool/model/agent version and place it in `QUALIFICATION`.
2. Capture exact version/digest and compatibility profile.
3. Build a separate immutable release artifact and record its SHA-256.
4. Run conformance and synthetic end-to-end certification suites.
5. Run shadow or canary evaluation; high-risk routing remains disabled before success.
6. Verify schema/adapter/policy/profile compatibility and migration plan.
7. Verify rollback plan independently.
8. Promote only after required evidence exists.
9. Perform post-upgrade verification and reconcile project state.
10. If verification fails, degrade/disable the candidate and execute the authorized rollback path.

The running platform may never replace its own active control/policy components merely because an update exists.
