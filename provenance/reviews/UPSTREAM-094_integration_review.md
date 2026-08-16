# UPSTREAM-094 — sigstore/cosign Integration Review

- License: `Apache-2.0`
- Inspected revision: `8b8c87b68a75f70c12e1adf25f9bb87f24abea7e`
- Candidate subsystem: `security_supply_chain`
- Review state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Integration outcome: `OPTIONAL_ADAPTER_IMPLEMENTED` or `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- Live qualification: `NOT_LIVE_VERIFIED`

## Source areas inspected

- `README.md`

## Useful concepts

- OCI signature verification
- keyless verification
- public-key verification
- digest-bound trust

## Integration decision

- Expose verification-only cosign adapter requiring immutable sha256 image references.

## Engineering findings

- Architecture: Verify artifact identity/digest before trust; signing belongs to a separately approved release authority.
- Security: Keyless signing may publish identity into transparency logs, so Round 3 integrates verification only.
- Portability: External Go binary with published platform assets.
- Maintenance: Trust roots and expected identities/issuers require lifecycle governance.
- Maturity: Core Sigstore project with stable verification workflows.
- Compatibility: Strong fit for supply-chain verification and later release gates.
- Dependency implications: External cosign binary and registry/TUF access for normal verification.

## Evidence

- `GitHub:sigstore/cosign@8b8c87b68a75f70c12e1adf25f9bb87f24abea7e`
- `README.md`
