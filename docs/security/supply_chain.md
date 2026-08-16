# Supply-chain security

Project Pipeline generates an internal SBOM from the pinned Python environment and concrete upstream integrations, checks workflow permissions and action pinning, records artifact SHA-256 integrity, and emits release provenance that links source aggregate, builder identity, SBOM digest, and verification evidence.

The external portfolio is layered: Trivy for vulnerability/misconfiguration/secret/license/SBOM evidence; Gitleaks for secrets; OSV-Scanner for vulnerable dependencies; Scorecard for repository posture; Cosign for artifact verification/signing boundaries; Zizmor for GitHub Actions audit; Harden-Runner for CI runner/network telemetry. External findings are normalized into `SupplyChainFinding`; only Project Pipeline's deterministic gate decides whether they block a release.
