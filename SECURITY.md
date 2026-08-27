# Security Policy

Security reports are handled privately and separately from ordinary support or bug reports.

## Supported versions

| Surface | Security support |
| --- | --- |
| Current `main` branch | Supported |
| Latest published release | Supported when a release is available |
| Older commits, forks, and modified builds | Not supported |

## Report a vulnerability

Use GitHub's [private vulnerability-reporting form](https://github.com/KevinSGarrett/ProjectPipeline/security/advisories/new). **Do not disclose a suspected vulnerability in a public issue, pull request, discussion, log, or screenshot.**

Please include, when available:

- the affected version, commit, component, or configuration;
- a clear description of the issue and its potential impact;
- minimal reproduction steps or a proof of concept;
- relevant environment details;
- any mitigation or remediation you have already identified.

Remove tokens, private keys, personal information, customer data, and unrelated private project content before attaching evidence. If the report itself requires sensitive material, explain what is available before transmitting it.

## What to expect

The maintainer will acknowledge the report, investigate it privately, and coordinate disclosure after a fix or practical mitigation is available. Additional details may be requested to reproduce or scope the issue. Public credit is welcome when requested, but never required.

## Security expectations

- Never commit credentials, private keys, access tokens, production connection strings, or private project data.
- Configure optional integrations with least privilege and narrowly scoped credentials.
- Treat imported code, model output, dependencies, and generated artifacts as untrusted until reviewed.
- Keep external writes explicit, authorized, idempotent where possible, and recoverable.
- Report accidental secret exposure privately and rotate affected credentials immediately.

For non-security help, use [SUPPORT.md](SUPPORT.md).
