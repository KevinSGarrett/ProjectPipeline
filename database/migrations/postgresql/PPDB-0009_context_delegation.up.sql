CREATE TABLE IF NOT EXISTS context_delegations (
    delegation_id TEXT PRIMARY KEY,
    payload_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS context_packs (
    pack_id TEXT PRIMARY KEY,
    delegation_id TEXT NOT NULL REFERENCES context_delegations(delegation_id),
    content_sha256 TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_context_packs_delegation ON context_packs(delegation_id, created_at_utc);
CREATE TABLE IF NOT EXISTS context_receipts (
    receipt_id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL REFERENCES context_packs(pack_id),
    status TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_context_receipts_pack ON context_receipts(pack_id, created_at_utc);
