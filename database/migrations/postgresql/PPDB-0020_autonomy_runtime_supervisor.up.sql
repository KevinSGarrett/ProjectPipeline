CREATE TABLE IF NOT EXISTS autonomy_runtime_meta (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS autonomy_runtime_operations (
    operation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    state TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    worker_id TEXT,
    base_branch TEXT,
    worktree_path TEXT,
    lease_fence TEXT,
    attempt INTEGER NOT NULL,
    result_fingerprint TEXT,
    verification_fingerprint TEXT,
    integrated_ref TEXT,
    incident TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_autonomy_runtime_operations_state
    ON autonomy_runtime_operations(state, updated_at_utc);
CREATE TABLE IF NOT EXISTS autonomy_runtime_receipts (
    operation_id TEXT PRIMARY KEY,
    receipt_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES autonomy_runtime_operations(operation_id)
);
CREATE TABLE IF NOT EXISTS autonomy_runtime_completed_tasks (
    task_id TEXT PRIMARY KEY,
    completed_at_utc TEXT NOT NULL,
    operation_id TEXT,
    verified_sha TEXT
);
