-- PPDB-0013 verification harness and executable evidence
CREATE TABLE verification_tool_activations (
    activation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    upstream_id TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX idx_verification_tool_activations_project
    ON verification_tool_activations(project_id, upstream_id);

CREATE TABLE verification_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    profile TEXT NOT NULL,
    final_state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    completed_at_utc TEXT NOT NULL
);
CREATE INDEX idx_verification_runs_project
    ON verification_runs(project_id, completed_at_utc);

CREATE TABLE verification_check_results (
    run_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    category TEXT NOT NULL,
    state TEXT NOT NULL,
    required INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(run_id, check_id),
    FOREIGN KEY(run_id) REFERENCES verification_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE verification_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES verification_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE verification_golden_journey_results (
    result_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    journey_id TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX idx_verification_golden_project
    ON verification_golden_journey_results(project_id, journey_id);
