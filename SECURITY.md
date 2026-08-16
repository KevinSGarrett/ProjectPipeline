
# Security Policy

## Reporting

Do not publish suspected vulnerabilities, credentials, or sensitive operational details in a public issue. Use the repository owner's private security-reporting channel when one is configured.

## Repository requirements

- Never commit real credentials, API keys, private keys, passwords, session tokens, or production connection strings.
- Keep external writes disabled by default.
- Treat generated or imported code as untrusted until reviewed and verified.
- Record third-party provenance and licensing before incorporation.
- Require validation of action intent, target, authority, scope, and idempotency before mutation.
- Preserve an audit event for security-sensitive actions.

## Supported state

This foundation implements repository-level safety checks and action-intent contracts. Runtime identity, policy enforcement, secrets management, egress control, signing, and complete supply-chain enforcement remain planned work and must not be described as live controls.
