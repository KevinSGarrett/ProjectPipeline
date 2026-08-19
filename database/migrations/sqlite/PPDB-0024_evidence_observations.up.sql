CREATE TABLE IF NOT EXISTS evidence_observations (
    observation_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    subject_sha TEXT NOT NULL,
    subject_tree TEXT NOT NULL,
    acceptance_scope_fingerprint TEXT NOT NULL,
    result TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    superseded_by TEXT,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_observations_lookup
    ON evidence_observations(evidence_id, subject_sha, subject_tree, recorded_at_utc);

CREATE TABLE IF NOT EXISTS evidence_observation_journal (
    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);
