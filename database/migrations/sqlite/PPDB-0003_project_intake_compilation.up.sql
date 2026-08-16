CREATE TABLE intake_compilations (
    compilation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    intake_mode TEXT NOT NULL,
    adoption_stage TEXT NOT NULL,
    target_root TEXT NOT NULL,
    repository_fingerprint TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    semantic_fingerprint TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    compiled_at_utc TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL
);

CREATE INDEX idx_intake_compilations_project
ON intake_compilations(project_id, compiled_at_utc, compilation_id);

CREATE TABLE bootstrap_receipts (
    receipt_id TEXT PRIMARY KEY,
    bootstrap_id TEXT NOT NULL,
    compilation_id TEXT NOT NULL REFERENCES intake_compilations(compilation_id) ON DELETE CASCADE,
    outcome TEXT NOT NULL,
    target_root TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL
);

CREATE INDEX idx_bootstrap_receipts_compilation
ON bootstrap_receipts(compilation_id, recorded_at_utc, bootstrap_id);
