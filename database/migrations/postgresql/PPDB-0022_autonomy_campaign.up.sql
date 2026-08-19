CREATE TABLE IF NOT EXISTS campaign_runs (
    campaign_id TEXT PRIMARY KEY,
    integrated_sha TEXT NOT NULL,
    integrated_tree TEXT NOT NULL,
    release_identity TEXT NOT NULL,
    stage TEXT NOT NULL,
    qualification_run_id TEXT,
    fence TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    service_identity TEXT,
    state_path TEXT NOT NULL,
    last_event_sha256 TEXT,
    started_at_utc TEXT NOT NULL,
    last_heartbeat_utc TEXT NOT NULL,
    next_transition TEXT,
    retry_budget INTEGER NOT NULL,
    last_probe TEXT,
    evidence_path TEXT NOT NULL,
    pp384_evidence_path TEXT NOT NULL,
    status TEXT NOT NULL,
    window_broken INTEGER NOT NULL DEFAULT 0,
    prior_campaign_id TEXT,
    lock_token TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaign_events (
    event_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prev_event_sha256 TEXT,
    event_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaign_runs(campaign_id)
);
CREATE TABLE IF NOT EXISTS campaign_command_receipts (
    receipt_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    command_json TEXT NOT NULL,
    command_sha256 TEXT NOT NULL,
    cwd TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT NOT NULL,
    exit_code INTEGER,
    stdout_sha256 TEXT,
    stderr_sha256 TEXT,
    stdout_tail TEXT,
    stderr_tail TEXT,
    result TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    retry_disposition TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    executed INTEGER NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaign_runs(campaign_id)
);
CREATE TABLE IF NOT EXISTS campaign_locks (
    lock_name TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    fence TEXT NOT NULL,
    acquired_at_utc TEXT NOT NULL
);
