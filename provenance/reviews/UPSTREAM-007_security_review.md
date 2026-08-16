# UPSTREAM-007 — Aqua Trivy security review

- Repository: `aquasecurity/trivy`
- Inspected revision: `d98911ea338b061f8bef0baeef85b35660013b32`
- License: `Apache-2.0`
- Disposition: retain `ADOPT_DEPENDENCY`; implement an optional external CLI adapter.

## Source-level findings
Trivy's current filesystem command supports `vuln`, `secret`, `misconfig`, and `license` scanners, JSON/SARIF/CycloneDX/SPDX outputs, explicit offline scanning, database/check-update controls, and telemetry disablement. Project Pipeline therefore uses Trivy as a read-only evidence producer for filesystem vulnerability, secret, misconfiguration, license, and SBOM checks. Network access remains explicit and the Trivy result is normalized into Project Pipeline findings before any release/blocking decision.

## Authority boundary
Trivy never authorizes, deploys, mutates project state, or declares security completion. Project Pipeline's deterministic Supply Chain Gate remains authoritative.
