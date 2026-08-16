CREATE TABLE IF NOT EXISTS budget_limits (
    limit_id TEXT PRIMARY KEY,
    scope_key TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    hard_cap_microunits INTEGER NOT NULL,
    protected_reserve_microunits INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(scope_key, cycle_id)
);
CREATE INDEX IF NOT EXISTS idx_budget_limits_scope ON budget_limits(scope_key, cycle_id);

CREATE TABLE IF NOT EXISTS budget_quota_limits (
    quota_id TEXT PRIMARY KEY,
    scope_key TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    quota_name TEXT NOT NULL,
    capacity_units INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(scope_key, provider_id, quota_name)
);
CREATE INDEX IF NOT EXISTS idx_budget_quota_scope ON budget_quota_limits(scope_key, provider_id);

CREATE TABLE IF NOT EXISTS budget_ledger (
    entry_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    task_id TEXT,
    provider_id TEXT,
    cost_class TEXT NOT NULL,
    direction TEXT NOT NULL,
    cash_microunits INTEGER NOT NULL,
    shadow_cost_microunits INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_ledger_project_time ON budget_ledger(project_id, observed_at_utc);
CREATE INDEX IF NOT EXISTS idx_budget_ledger_task ON budget_ledger(task_id, observed_at_utc);
CREATE INDEX IF NOT EXISTS idx_budget_ledger_provider ON budget_ledger(provider_id, observed_at_utc);

CREATE TABLE IF NOT EXISTS budget_spend_leases (
    lease_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    provider_id TEXT,
    state TEXT NOT NULL,
    reserved_microunits INTEGER NOT NULL,
    consumed_microunits INTEGER NOT NULL,
    expires_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_spend_leases_active ON budget_spend_leases(state, expires_at_utc);
CREATE INDEX IF NOT EXISTS idx_budget_spend_leases_project ON budget_spend_leases(project_id, state);

CREATE TABLE IF NOT EXISTS budget_admission_decisions (
    decision_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    admitted INTEGER NOT NULL,
    pressure_mode TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_admission_task ON budget_admission_decisions(task_id, created_at_utc);

CREATE TABLE IF NOT EXISTS budget_cost_history (
    observation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_class TEXT NOT NULL,
    provider_id TEXT,
    cash_microunits INTEGER NOT NULL,
    verified INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_history_class_provider ON budget_cost_history(task_class, provider_id, observed_at_utc);

CREATE TABLE IF NOT EXISTS budget_anomalies (
    anomaly_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    provider_id TEXT,
    severity TEXT NOT NULL,
    block_new_paid_work INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    detected_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_anomaly_project ON budget_anomalies(project_id, detected_at_utc);

CREATE TABLE IF NOT EXISTS budget_forecasts (
    forecast_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_class TEXT,
    provider_id TEXT,
    p50_microunits INTEGER NOT NULL,
    p90_microunits INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    generated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_forecast_project ON budget_forecasts(project_id, generated_at_utc);
