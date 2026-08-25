# Secrets, data classification, and egress

Secrets are represented by capability references. A `SecretLease` binds identity, project, target, operation, expiry, and issuing authority. Plaintext is materialized only into an `EphemeralSecret`; its representation and metadata expose only a SHA-256 fingerprint and lease metadata. Persistent state stores secret references and leases, not plaintext.

Local ENV/FILE references are supported through the configuration resolver. SOPS and age provide encrypted-file materialization boundaries. OpenBao is an optional network secret backend and requires explicit network authorization. All backends sit behind the same Secrets Broker contract.

## CPU campaign credentials

Cycle 16-B's CPU-owned campaign may use only the current-user
`dpapi://C16B_JIRA_TOKEN` and `dpapi://C16B_GITHUB_TOKEN` references. The
GitHub token is never taken from an ambient GitHub CLI session during an
unattended campaign; both references are scope-checked against the CPU,
scheduled Windows SID, lease, expiry, and campaign deadline before use.
Its non-secret runtime configuration binds the project, cycle, CPU hostname,
Windows SID, lease identity, credential expiry, and campaign deadline. New
admission verifies a fresh bounded lease; recovery verifies that the existing
lease remains unexpired through the bound deadline. Revocation requires the
same full scope, writes a durable non-secret intent before deleting the
encrypted envelope, and reconciles an interrupted deletion on the next run.
Plaintext is never placed in the runtime configuration, receipt, command line,
repository, or artifact.

Data is classified PUBLIC, INTERNAL, CONFIDENTIAL, SECRET, or LOCAL_ONLY. Secret and local-only data cannot egress. Confidential egress requires approval. Untrusted instructions may be transferred only as constrained data and cannot acquire governing authority.
