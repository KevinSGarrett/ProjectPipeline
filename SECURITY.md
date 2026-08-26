# Security Policy

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue or discussion. Use GitHub's private vulnerability-reporting flow for this repository. Include a clear description, affected version or commit, reproduction steps, impact, and any suggested mitigation.

We will acknowledge reports, investigate them privately, and coordinate disclosure after a fix or mitigation is available. We may ask for clarification, but will not ask you to publish sensitive details.

## Supported surface

ProjectPipeline is in active development. Security fixes are assessed against the current default branch and the latest published release. Optional integrations and local developer tooling should be configured with least privilege and must never receive credentials through an issue, pull request, discussion, or log.

## Security expectations

- Never commit credentials, private keys, tokens, production connection strings, or private project data.
- Treat imported code, dependencies, and generated artifacts as untrusted until reviewed.
- Keep external writes explicit, scoped, and recoverable.
- Report accidental secret exposure privately and promptly.
