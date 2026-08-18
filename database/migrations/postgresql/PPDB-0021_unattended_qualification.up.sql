CREATE TABLE IF NOT EXISTS qualification_runs (
    run_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    state_path TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    last_heartbeat_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    attested_elapsed_seconds DOUBLE PRECISION NOT NULL,
    fence TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    prior_run_id TEXT,
    window_broken INTEGER NOT NULL DEFAULT 0,
    last_event_sha256 TEXT,
    heartbeat_cadence_seconds DOUBLE PRECISION NOT NULL,
    lock_token TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qualification_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prev_event_sha256 TEXT,
    event_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES qualification_runs(run_id)
);
CREATE TABLE IF NOT EXISTS qualification_locks (
    lock_name TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    fence TEXT NOT NULL,
    acquired_at_utc TEXT NOT NULL
);
