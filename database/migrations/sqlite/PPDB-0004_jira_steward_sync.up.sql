CREATE TABLE jira_remote_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    project_key TEXT NOT NULL,
    source TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
    snapshot_json TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL
);

CREATE INDEX idx_jira_remote_snapshots_project
ON jira_remote_snapshots(project_key, observed_at_utc, snapshot_id);

CREATE TABLE jira_reconciliation_plans (
    plan_id TEXT PRIMARY KEY,
    project_key TEXT NOT NULL,
    authority_mode TEXT NOT NULL,
    local_fingerprint TEXT NOT NULL,
    remote_snapshot_id TEXT NOT NULL REFERENCES jira_remote_snapshots(snapshot_id),
    remote_fingerprint TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX idx_jira_reconciliation_plans_project
ON jira_reconciliation_plans(project_key, created_at_utc, plan_id);

CREATE TABLE jira_sync_operations (
    operation_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES jira_reconciliation_plans(plan_id) ON DELETE CASCADE,
    operation_type TEXT NOT NULL,
    local_id TEXT,
    remote_key TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_fingerprint TEXT NOT NULL,
    operation_state TEXT NOT NULL,
    requires_remote_write INTEGER NOT NULL CHECK (requires_remote_write IN (0, 1)),
    requires_human_approval INTEGER NOT NULL CHECK (requires_human_approval IN (0, 1)),
    operation_json TEXT NOT NULL,
    error_json TEXT,
    external_operation_id TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX idx_jira_sync_operations_outbox
ON jira_sync_operations(operation_state, requires_remote_write, updated_at_utc, operation_id);

CREATE TABLE jira_remote_mappings (
    local_id TEXT PRIMARY KEY,
    remote_key TEXT NOT NULL UNIQUE,
    provider_id TEXT NOT NULL,
    first_observed_at_utc TEXT NOT NULL,
    last_observed_at_utc TEXT NOT NULL,
    source_operation_id TEXT REFERENCES jira_sync_operations(operation_id),
    remote_fingerprint TEXT
);

CREATE TABLE jira_sync_receipts (
    receipt_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES jira_reconciliation_plans(plan_id),
    mode TEXT NOT NULL,
    result TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX idx_jira_sync_receipts_plan
ON jira_sync_receipts(plan_id, created_at_utc, receipt_id);
