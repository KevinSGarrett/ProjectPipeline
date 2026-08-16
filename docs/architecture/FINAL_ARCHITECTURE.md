# Final Architecture Baseline for Release Hardening

This document is the Pass 24 release-hardening architecture baseline; Pass 25 remains the convergence/final-audit pass.

Project Pipeline is local-primary. Canonical state and deterministic control remain in the project-owned persistence/control/assurance planes. Optional upstream components are adapters, runtimes, evidence producers, or mechanics behind owned contracts. Operator clients are projections, not state authorities. External writes are typed, policy-gated, credential-scoped, idempotent where applicable, reconciled after uncertain outcomes, and auditable.

Deployment profiles are local Python, Windows service/desktop, container, and optional hybrid AWS recovery-spine. Pass 24 source-implements the missing Windows-service and Docker boundaries while preserving truthful target qualification. The current environment verifies local Python behavior only; Windows, Docker, Terraform/AWS, and unavailable external security tooling remain separately unqualified.

Safe platform upgrades use isolated candidate development, independent certification, synthetic/shadow execution, verified backup/restore material, standby-first upgrade, compatibility checks, controlled handoff, observation, and deterministic rollback. A running Director cannot independently certify or promote its own replacement.
