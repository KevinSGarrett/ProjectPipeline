CREATE TABLE IF NOT EXISTS scheduler_resource_pools (
    resource_key TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    capacity_units INTEGER NOT NULL,
    reserved_units INTEGER NOT NULL,
    machine_id TEXT,
    observed INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scheduler_fencing_tokens (
    resource_key TEXT PRIMARY KEY,
    current_token INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS scheduler_resource_leases (
    lease_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    holder_id TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    access_mode TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    fencing_token INTEGER NOT NULL,
    acquired_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL,
    released_at_utc TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduler_leases_resource ON scheduler_resource_leases(resource_key, released_at_utc, expires_at_utc);
CREATE INDEX IF NOT EXISTS idx_scheduler_leases_task ON scheduler_resource_leases(task_id, released_at_utc, expires_at_utc);
CREATE TABLE IF NOT EXISTS scheduler_plans (
    plan_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    control_snapshot_id TEXT NOT NULL,
    registry_id TEXT NOT NULL,
    backpressure_mode TEXT NOT NULL,
    lane_count INTEGER NOT NULL,
    candidate_count INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduler_plans_project ON scheduler_plans(project_id, created_at_utc);
CREATE TABLE IF NOT EXISTS scheduler_simulations (
    simulation_id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    assertions_passed INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
