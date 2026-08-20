CREATE TABLE IF NOT EXISTS retrieval_chunks (
    chunk_id TEXT PRIMARY KEY,
    source_reference TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding_model TEXT,
    embedding_version TEXT,
    embedding_json TEXT,
    recorded_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_source
    ON retrieval_chunks(source_reference, start_line, end_line);

CREATE TABLE IF NOT EXISTS retrieval_backup_receipts (
    receipt_id TEXT PRIMARY KEY,
    engine TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
