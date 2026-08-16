# UPSTREAM-053 — Infracost Budget Governor review

- Repository: `infracost/infracost`
- Inspected revision: `0c473ade0fd0d725fe8f5edd719ef634d9594690`
- License: Apache-2.0
- Source areas: `schema/infracost.schema.json`, JSON golden output, `LICENSE`.

## Decision

Implement an external CLI adapter that requests machine-readable Terraform/IaC cost estimates and normalizes project/resource totals, cost components, usage-based flags, and unknown-price markers. The adapter cannot apply infrastructure or authorize spend. Missing executable, invalid JSON, unsupported currency, or unknown pricing produces an unavailable/incomplete estimate rather than a fabricated zero.
