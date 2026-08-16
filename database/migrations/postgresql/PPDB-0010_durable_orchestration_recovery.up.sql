CREATE TABLE IF NOT EXISTS orchestration_workflow_definitions (
    definition_id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    version TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    UNIQUE(workflow_name, version)
);
CREATE TABLE IF NOT EXISTS orchestration_workflows (
    workflow_id TEXT PRIMARY KEY,
    definition_id TEXT NOT NULL REFERENCES orchestration_workflow_definitions(definition_id),
    idempotency_key TEXT NOT NULL,
    state TEXT NOT NULL,
    row_version BIGINT NOT NULL,
    backend TEXT NOT NULL,
    backend_run_id TEXT,
    assigned_worker_id TEXT,
    payload_json JSONB NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL,
    UNIQUE(definition_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_workflows_state ON orchestration_workflows(state, updated_at_utc);
CREATE INDEX IF NOT EXISTS idx_orchestration_workflows_worker ON orchestration_workflows(assigned_worker_id, state);
CREATE TABLE IF NOT EXISTS orchestration_events (
    event_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES orchestration_workflows(workflow_id),
    sequence BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    occurred_at_utc TIMESTAMPTZ NOT NULL,
    correlation_id TEXT,
    UNIQUE(workflow_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_events_workflow ON orchestration_events(workflow_id, sequence);
CREATE TABLE IF NOT EXISTS orchestration_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES orchestration_workflows(workflow_id),
    step_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orchestration_checkpoints_workflow ON orchestration_checkpoints(workflow_id, created_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_waits (
    wait_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES orchestration_workflows(workflow_id),
    kind TEXT NOT NULL,
    signal_name TEXT,
    release_at_utc TIMESTAMPTZ,
    satisfied_at_utc TIMESTAMPTZ,
    payload_json JSONB NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orchestration_waits_due ON orchestration_waits(satisfied_at_utc, release_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_workers (
    worker_id TEXT PRIMARY KEY,
    fencing_epoch BIGINT NOT NULL,
    payload_json JSONB NOT NULL,
    observed_at_utc TIMESTAMPTZ NOT NULL,
    expires_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orchestration_workers_expiry ON orchestration_workers(expires_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_inbox (
    message_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES orchestration_workflows(workflow_id),
    message_type TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    received_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orchestration_inbox_workflow ON orchestration_inbox(workflow_id, received_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_outbox (
    operation_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES orchestration_workflows(workflow_id),
    operation_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    backend TEXT NOT NULL,
    backend_operation_id TEXT,
    attempt_count INTEGER NOT NULL,
    last_error TEXT,
    created_at_utc TIMESTAMPTZ NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL,
    UNIQUE(workflow_id, operation_type, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_outbox_state ON orchestration_outbox(state, updated_at_utc);
CREATE TABLE IF NOT EXISTS orchestration_recovery_decisions (
    recovery_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES orchestration_workflows(workflow_id),
    action TEXT NOT NULL,
    safe_to_automate BOOLEAN NOT NULL,
    payload_json JSONB NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orchestration_recovery_workflow ON orchestration_recovery_decisions(workflow_id, created_at_utc);
