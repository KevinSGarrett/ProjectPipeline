CREATE TABLE IF NOT EXISTS campaign_owner_bindings (
    lock_name TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    qualification_run_id TEXT,
    fence TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    executable_identity TEXT NOT NULL,
    process_started_at_utc TEXT NOT NULL,
    service_identity TEXT,
    claimed_at_utc TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaign_runs(campaign_id)
);
