# UPSTREAM-081 — OSSF Scorecard security review

- Repository: `ossf/scorecard`
- Inspected revision: `d1fab88f54636ff366076edfc5c239f97b3c8e66`
- License: `Apache-2.0`
- Disposition: retain `ADOPT_DEPENDENCY`; implement an optional network CLI posture adapter.

## Source-level findings
Scorecard's documented checks cover repository supply-chain posture such as branch protection, dangerous workflows, token permissions, pinned dependencies, maintained status, packaging, dependency update tooling, signed releases, security policy, and vulnerability handling. Project Pipeline treats this as posture evidence for a GitHub repository, never as a replacement for its own policy/evidence state.

## Authority boundary
Live execution requires explicit network authorization. A score is evidence, not a release authorization or Completion Gate result.
