CREATE TABLE IF NOT EXISTS orchestration_workflow_definitions (
    definition_id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(workflow_name, version)
);
CREATE TABLE IF NOT EXISTS orchestration_workflows (
    workflow_id TEXT PRIMARY KEY,
    definition_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    state TEXT NOT NULL,
    row_version INTEGER NOT NULL,
    backend TEXT NOT NULL,
    backend_run_id TEXT,
    assigned_worker_id TEXT,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(definition_id, idempotency_key),
    FOREIGN KEY (definition_id) REFERENCES orchestration_workflow_definitions(definition_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_workflows_state ON orchestration_workflows(state, updated_at_utc);
CREATE INDEX IF NOT EXISTS idx_orchestration_workflows_worker ON orchestration_workflows(assigned_worker_id, state);
CREATE TABLE IF NOT EXISTS orchestration_events (
    event_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at_utc TEXT NOT NULL,
    correlation_id TEXT,
    UNIQUE(workflow_id, sequence),
    FOREIGN KEY (workflow_id) REFERENCES orchestration_workflows(workflow_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_events_workflow ON orchestration_events(workflow_id, sequence);
CREATE TABLE IF NOT EXISTS orchestration_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES orchestration_workflows(workflow_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_checkpoints_workflow ON orchestration_checkpoints(workflow_id, created_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_waits (
    wait_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    signal_name TEXT,
    release_at_utc TEXT,
    satisfied_at_utc TEXT,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES orchestration_workflows(workflow_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_waits_due ON orchestration_waits(satisfied_at_utc, release_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_workers (
    worker_id TEXT PRIMARY KEY,
    fencing_epoch INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orchestration_workers_expiry ON orchestration_workers(expires_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_inbox (
    message_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    message_type TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES orchestration_workflows(workflow_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_inbox_workflow ON orchestration_inbox(workflow_id, received_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_outbox (
    operation_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    backend TEXT NOT NULL,
    backend_operation_id TEXT,
    attempt_count INTEGER NOT NULL,
    last_error TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(workflow_id, operation_type, idempotency_key),
    FOREIGN KEY (workflow_id) REFERENCES orchestration_workflows(workflow_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_outbox_state ON orchestration_outbox(state, updated_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_recovery_decisions (
    recovery_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    action TEXT NOT NULL,
    safe_to_automate INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES orchestration_workflows(workflow_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_recovery_workflow ON orchestration_recovery_decisions(workflow_id, created_at_utc);
