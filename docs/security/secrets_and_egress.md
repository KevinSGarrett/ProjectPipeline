# Secrets, data classification, and egress

Secrets are represented by capability references. A `SecretLease` binds identity, project, target, operation, expiry, and issuing authority. Plaintext is materialized only into an `EphemeralSecret`; its representation and metadata expose only a SHA-256 fingerprint and lease metadata. Persistent state stores secret references and leases, not plaintext.

Local ENV/FILE references are supported through the configuration resolver. SOPS and age provide encrypted-file materialization boundaries. OpenBao is an optional network secret backend and requires explicit network authorization. All backends sit behind the same Secrets Broker contract.

## CPU campaign credentials

Cycle 16-B's CPU-owned campaign may use only the current-user
`dpapi://C16B_JIRA_TOKEN` and `dpapi://C16B_GITHUB_TOKEN` references. The
GitHub token is never taken from an ambient GitHub CLI session during an
unattended campaign; both references are current-user encrypted credential
envelopes, not multi-day plaintext secret leases. An envelope is bound to the
CPU hostname, scheduled Windows SID, project, cycle, campaign identity,
candidate SHA/tree, scheduler lease, fencing token, and campaign deadline.
The envelope may retain ciphertext only until that bounded deadline.

Each materialization creates a separate in-memory access lease with an access
identity and a TTL no longer than `secret_lease_max_seconds` in
`config/security_policy.json` (currently 900 seconds). A missing, expired,
revoked, wrong-machine, wrong-principal, wrong-campaign, wrong-candidate, or
stale-fence access context fails closed before DPAPI decryption. Recovery
creates a new access lease and resolves the same encrypted reference; it never
stores plaintext for later use. A stale timed runner is disqualified in place:
its recovery task cannot create or retarget a successor under the parent
credential scope. A replacement campaign must receive fresh governed runtime,
lease, fence, and credential-envelope identities. The scheduled campaign
environment contains
only non-secret endpoint metadata, references, binding identifiers, and the
CPU-local campaign database path. Before any campaign DPAPI materialization,
the runtime scope must agree with the checkout's `HEAD` and tree and with the
selected `campaign_runs` row, including its campaign ID, SHA/tree, lease, and
fence. The controller database argument must be the same absolute database
path named by that runtime binding, preventing a split between a credential
record and the campaign it operates. The recovery task's config campaign ID
must also equal the runtime binding before it can construct a controller or
write status. A scheduled campaign process never loads
the checkout `.env`; it clears inherited configuration after parsing the
runtime file, and the hidden runner, recovery task, and every allowlisted child
command use only its explicit allowlist rather than ambient variables.

Provisioning accepts plaintext only on standard input, immediately encrypts it
under the CPU current-user DPAPI identity, restricts the envelope ACL to the
scheduled SID, reads that ACL back to allow only that SID or its exact
same-SID account-name resolution, rejects every additional trustee, and emits
only redacted metadata. Revocation requires the same
full scope, records a durable non-secret intent before deletion, and reconciles
an interrupted deletion idempotently on the next run. Plaintext is never
placed in a runtime configuration, receipt, command line, database, repository,
or artifact.

Data is classified PUBLIC, INTERNAL, CONFIDENTIAL, SECRET, or LOCAL_ONLY. Secret and local-only data cannot egress. Confidential egress requires approval. Untrusted instructions may be transferred only as constrained data and cannot acquire governing authority.
