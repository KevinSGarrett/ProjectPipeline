# Pass 24 Hardening and Packaging Upstream Review

The Pass 24 gate re-opens the twelve hardening candidates before packaging decisions. Trivy, Gitleaks, OSV-Scanner, Infracost, Scorecard, Cosign, restic, act, Harden-Runner, and WinSW remain bounded evidence/mechanics/runtime candidates. They do not own Project Pipeline policy, budget, completion, release, or canonical state.

k6 and Renovate are AGPL-3.0-only in the reviewed upstream state and remain blocked from activation by the current Project Pipeline license policy. Performance evidence therefore uses the internal deterministic measurement harness in this environment rather than activating k6.

The quality workflow already uses a reviewed immutable Harden-Runner SHA. This verifies configuration provenance only; hosted CI execution remains a separate environment observation. WinSW source packaging is added without vendoring an executable. The binary must be acquired separately, pinned by digest, carry its license notice, and be exercised on Windows before service-runtime qualification.

Current build-environment observation: Docker, Terraform, PowerShell, Rust/Cargo, and the external scanner/signing/backup CLIs in this cohort are unavailable. Their source/configuration boundaries can be tested, but no live target/tool success is claimed.
