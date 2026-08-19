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

INSERT INTO campaign_owner_bindings (
    lock_name, campaign_id, qualification_run_id, fence, lease_id, process_id,
    executable_identity, process_started_at_utc, service_identity, claimed_at_utc
)
SELECT
    locks.lock_name,
    locks.campaign_id,
    runs.qualification_run_id,
    locks.fence,
    runs.lease_id,
    locks.process_id,
    '',
    '',
    runs.service_identity,
    COALESCE(locks.acquired_at_utc, runs.started_at_utc)
FROM campaign_locks AS locks
INNER JOIN campaign_runs AS runs ON runs.campaign_id = locks.campaign_id
WHERE locks.lock_name = 'active-campaign';
