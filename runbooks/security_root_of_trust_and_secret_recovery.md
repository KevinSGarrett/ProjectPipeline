# Root-of-trust and secret recovery runbook

1. Suspend the affected identity or secret reference and revoke active capability grants and secret leases.
2. Preserve current audit evidence and repository/evidence manifests before changing trust material.
3. Re-establish control through an authorized human bootstrap identity; do not let the affected agent/service approve the recovery.
4. Create a replacement key or secret reference. For encrypted configuration, re-encrypt and validate through SOPS/age before switching references.
5. Update the root-of-trust reference, run security and full repository verification, then revoke the superseded credential.
6. If provenance or artifact integrity is uncertain, treat release material as untrusted and rebuild from a verified source state.
7. Record independent security approval, recovery evidence, and any externally blocked follow-up.
