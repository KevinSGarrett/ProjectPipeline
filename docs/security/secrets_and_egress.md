# Secrets, data classification, and egress

Secrets are represented by capability references. A `SecretLease` binds identity, project, target, operation, expiry, and issuing authority. Plaintext is materialized only into an `EphemeralSecret`; its representation and metadata expose only a SHA-256 fingerprint and lease metadata. Persistent state stores secret references and leases, not plaintext.

Local ENV/FILE references are supported through the configuration resolver. SOPS and age provide encrypted-file materialization boundaries. OpenBao is an optional network secret backend and requires explicit network authorization. All backends sit behind the same Secrets Broker contract.

Data is classified PUBLIC, INTERNAL, CONFIDENTIAL, SECRET, or LOCAL_ONLY. Secret and local-only data cannot egress. Confidential egress requires approval. Untrusted instructions may be transferred only as constrained data and cannot acquire governing authority.
