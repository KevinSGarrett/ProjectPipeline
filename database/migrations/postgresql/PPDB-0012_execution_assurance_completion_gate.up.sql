CREATE TABLE IF NOT EXISTS assurance_verification_plans (
  plan_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assurance_verification_plans_project ON assurance_verification_plans(project_id);
CREATE TABLE IF NOT EXISTS assurance_truth_records (
  truth_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assurance_truth_records_project ON assurance_truth_records(project_id);
CREATE TABLE IF NOT EXISTS assurance_reviews (
  review_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assurance_reviews_project ON assurance_reviews(project_id);
CREATE TABLE IF NOT EXISTS assurance_loop_decisions (
  decision_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assurance_loop_decisions_project ON assurance_loop_decisions(project_id);
CREATE TABLE IF NOT EXISTS assurance_scope_contracts (
  scope_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assurance_scope_contracts_project ON assurance_scope_contracts(project_id);
CREATE TABLE IF NOT EXISTS assurance_scope_changes (
  change_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assurance_scope_changes_project ON assurance_scope_changes(project_id);
CREATE TABLE IF NOT EXISTS assurance_gate_evaluations (
  gate_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assurance_gate_evaluations_project ON assurance_gate_evaluations(project_id);
