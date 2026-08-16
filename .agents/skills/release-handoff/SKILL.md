---
name: release-handoff
description: Build, verify, publish when authorized, and hand off a ProjectPipeline release with evidence and rollback.
---

# Release and Handoff

1. Read instructions `09`, `12`, and `19`.
2. Fix exact release SHA/version/scope and confirm Jira/requirement disposition.
3. Run release-tier tests, security/supply-chain checks, applicable PPQS, install/upgrade, and recovery verification.
4. Build deterministic artifacts with SBOM, hashes, provenance, and no local secrets/state.
5. Publish only with policy authority; reconcile uncertain publication outcomes.
6. Verify the published artifact and integrated SHA.
7. Produce the release handoff with accurate live/mock/partial/blocked/unknown states.
8. Reconcile Jira/evidence and clean only eligible branches, worktrees, and test resources.
