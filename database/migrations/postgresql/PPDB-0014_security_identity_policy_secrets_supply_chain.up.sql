-- PPDB-0014 security identity, policy, secrets metadata, and supply-chain evidence
CREATE TABLE security_identities (identity_id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE security_capability_grants (grant_id TEXT PRIMARY KEY, identity_id TEXT NOT NULL, capability TEXT NOT NULL, expires_at_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL);
CREATE INDEX idx_security_grants_identity ON security_capability_grants(identity_id, capability);
CREATE TABLE security_approvals (approval_id TEXT PRIMARY KEY, action_id TEXT NOT NULL, decision TEXT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE security_policy_decisions (decision_id TEXT PRIMARY KEY, action_id TEXT NOT NULL, disposition TEXT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE security_egress_decisions (decision_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, disposition TEXT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE security_secret_references (secret_ref_id TEXT PRIMARY KEY, backend TEXT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE security_secret_leases (lease_id TEXT PRIMARY KEY, secret_ref_id TEXT NOT NULL, identity_id TEXT NOT NULL, expires_at_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL);
CREATE INDEX idx_security_secret_leases_identity ON security_secret_leases(identity_id, expires_at_utc);
CREATE TABLE security_audit_events (audit_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, occurred_at_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE security_sboms (sbom_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE security_supply_chain_gates (gate_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, state TEXT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE security_root_trust (root_id TEXT PRIMARY KEY, bootstrap_identity_id TEXT NOT NULL, payload_json JSONB NOT NULL);
