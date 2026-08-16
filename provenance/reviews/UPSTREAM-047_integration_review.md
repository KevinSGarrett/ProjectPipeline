# UPSTREAM-047 — google/osv-scanner Integration Review

- License: `Apache-2.0`
- Inspected revision: `567f3ea998f1241e60ec3ca9c4cc9e30809cd820`
- Candidate subsystem: `security_supply_chain`
- Review state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Integration outcome: `OPTIONAL_ADAPTER_IMPLEMENTED` or `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- Live qualification: `NOT_LIVE_VERIFIED`

## Source areas inspected

- `README.md`
- `docs/output.md`
- `LICENSE`

## Useful concepts

- dependency vulnerability scanning
- JSON output
- offline databases
- multi-ecosystem scanning

## Integration decision

- Expose read-only source scanning with JSON output; guided remediation is deliberately excluded from autonomous execution.

## Engineering findings

- Architecture: Separate finding vulnerabilities from risky package-manager remediation.
- Security: The upstream fix command can execute package-manager behavior and is prohibited by this adapter.
- Portability: Prebuilt binaries and many package ecosystems supported.
- Maintenance: Vulnerability database freshness matters; offline mode needs database lifecycle management later.
- Maturity: Google-supported OSV frontend with SLSA-oriented release posture.
- Compatibility: Strong dependency vulnerability gate.
- Dependency implications: External osv-scanner binary; online OSV/deps.dev network access is explicit.

## Evidence

- `GitHub:google/osv-scanner@567f3ea998f1241e60ec3ca9c4cc9e30809cd820`
- `README.md`
- `docs/output.md`
- `LICENSE`
