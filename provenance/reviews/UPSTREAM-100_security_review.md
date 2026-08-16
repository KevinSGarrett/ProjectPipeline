# UPSTREAM-100 — StepSecurity Harden-Runner review

- Repository: `step-security/harden-runner`
- Inspected revision: `05e31511f85b41b11d1cf0ef85d0992719546e2c`
- License: `Apache-2.0`
- Reviewed action pin: `f808768d1510423e83855289c910610ca9b43176` (`v2.17.0` in reviewed README)
- Disposition: retain `ADOPT_DEPENDENCY`; adopt the CI hardening profile.

## Source-level findings
Harden-Runner is designed for CI-specific process, network, and file telemetry. Its reviewed quick-start uses the action as the first job step with `egress-policy: audit`, pinned to an immutable SHA. Project Pipeline applies that exact reviewed pattern to the quality and dependency-audit jobs while keeping top-level GitHub token permissions read-only.

## Authority boundary
Harden-Runner telemetry and recommendations are evidence. CI authorization, supply-chain gating, and emergency action remain Project Pipeline deterministic policy decisions.
