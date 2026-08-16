CREATE TABLE IF NOT EXISTS github_resource_ownership (
    ownership_id TEXT PRIMARY KEY,
    repository_slug TEXT NOT NULL,
    resource_kind TEXT NOT NULL,
    resource TEXT NOT NULL,
    owner_task_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_github_resource_ownership_active ON github_resource_ownership(repository_slug, state, resource_kind, resource);
CREATE TABLE IF NOT EXISTS github_merge_gate_evaluations (
    gate_id TEXT PRIMARY KEY,
    repository_slug TEXT NOT NULL,
    pull_number INTEGER NOT NULL,
    head_sha TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    evaluated_at_utc TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS github_operations (
    operation_id TEXT PRIMARY KEY,
    operation_type TEXT NOT NULL,
    repository_slug TEXT NOT NULL,
    target TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    expected_head_sha TEXT,
    authorization_id TEXT,
    actor_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    observed_result_json JSONB,
    created_at_utc TIMESTAMPTZ NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_github_operations_state ON github_operations(repository_slug, state, updated_at_utc);
CREATE TABLE IF NOT EXISTS github_operation_receipts (
    receipt_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES github_operations(operation_id),
    state TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL
);
