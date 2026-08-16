CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    manifest_revision INTEGER NOT NULL CHECK (manifest_revision >= 1),
    manifest_fingerprint TEXT NOT NULL,
    manifest_json JSONB NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL
);

CREATE TABLE project_states (
    project_id TEXT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    version BIGINT NOT NULL CHECK (version >= 1),
    manifest_revision INTEGER NOT NULL CHECK (manifest_revision >= 1),
    blocked_reason TEXT,
    task_counts_json JSONB NOT NULL,
    last_transition_id TEXT,
    updated_at_utc TIMESTAMPTZ NOT NULL
);

CREATE TABLE task_states (
    task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    version BIGINT NOT NULL CHECK (version >= 1),
    priority TEXT NOT NULL,
    dependency_ids_json JSONB NOT NULL,
    blocker_ids_json JSONB NOT NULL,
    owner_id TEXT,
    blocked_reason TEXT,
    last_transition_id TEXT,
    updated_at_utc TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_task_states_project_state
ON task_states(project_id, state, priority, task_id);

CREATE TABLE state_transitions (
    transition_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    previous_state TEXT NOT NULL,
    next_state TEXT NOT NULL,
    expected_version BIGINT NOT NULL,
    resulting_version BIGINT NOT NULL,
    reason TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    occurred_at_utc TIMESTAMPTZ NOT NULL,
    transition_json JSONB NOT NULL
);

CREATE INDEX idx_state_transitions_entity
ON state_transitions(entity_type, entity_id, resulting_version);

CREATE TABLE system_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL
);
