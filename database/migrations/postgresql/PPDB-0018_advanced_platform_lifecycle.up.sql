CREATE TABLE IF NOT EXISTS lifecycle_portfolio_projects (
  project_id TEXT PRIMARY KEY,
  authority_id TEXT NOT NULL,
  state TEXT NOT NULL,
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  payload_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS lifecycle_environments (
  environment_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  environment_type TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  expires_at_utc TIMESTAMPTZ,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_environments_project ON lifecycle_environments(project_id, environment_type);
CREATE TABLE IF NOT EXISTS lifecycle_test_data_assets (
  asset_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  classification TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS lifecycle_contract_evolutions (
  evolution_id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS lifecycle_qualifications (
  qualification_id TEXT PRIMARY KEY,
  subject_kind TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  version TEXT NOT NULL,
  state TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_qual_subject ON lifecycle_qualifications(subject_kind, subject_id, state);
CREATE TABLE IF NOT EXISTS lifecycle_project_closures (
  project_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  payload_json JSONB NOT NULL
);
