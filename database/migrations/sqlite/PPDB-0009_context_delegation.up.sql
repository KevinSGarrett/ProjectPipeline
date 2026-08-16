CREATE TABLE IF NOT EXISTS context_delegations (
    delegation_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS context_packs (
    pack_id TEXT PRIMARY KEY,
    delegation_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (delegation_id) REFERENCES context_delegations(delegation_id)
);
CREATE INDEX IF NOT EXISTS idx_context_packs_delegation ON context_packs(delegation_id, created_at_utc);
CREATE TABLE IF NOT EXISTS context_receipts (
    receipt_id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (pack_id) REFERENCES context_packs(pack_id)
);
CREATE INDEX IF NOT EXISTS idx_context_receipts_pack ON context_receipts(pack_id, created_at_utc);
