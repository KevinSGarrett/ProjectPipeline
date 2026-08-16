CREATE TABLE control_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    graph_fingerprint TEXT NOT NULL,
    snapshot_fingerprint TEXT NOT NULL,
    ready_count INTEGER NOT NULL,
    active_count INTEGER NOT NULL,
    blocked_count INTEGER NOT NULL,
    scope_finding_count INTEGER NOT NULL,
    completion_state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX idx_control_snapshots_project_created
    ON control_snapshots(project_id, created_at_utc);
CREATE TABLE control_sequence_items (
    snapshot_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    readiness TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    on_critical_path INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, task_id),
    FOREIGN KEY(snapshot_id) REFERENCES control_snapshots(snapshot_id) ON DELETE CASCADE
);
CREATE INDEX idx_control_sequence_items_snapshot_rank
    ON control_sequence_items(snapshot_id, rank);
CREATE TABLE control_scope_findings (
    snapshot_id TEXT NOT NULL,
    finding_order INTEGER NOT NULL,
    kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    related_id TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, finding_order),
    FOREIGN KEY(snapshot_id) REFERENCES control_snapshots(snapshot_id) ON DELETE CASCADE
);
