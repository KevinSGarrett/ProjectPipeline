
CREATE TABLE agent_registry_snapshots (registry_id TEXT PRIMARY KEY, payload_json JSONB NOT NULL, created_at_utc TIMESTAMPTZ NOT NULL);
CREATE TABLE agent_provider_states (provider_id TEXT PRIMARY KEY, state TEXT NOT NULL, payload_json JSONB NOT NULL, observed_at_utc TIMESTAMPTZ NOT NULL);
CREATE TABLE agent_circuit_breakers (provider_id TEXT PRIMARY KEY, circuit_state TEXT NOT NULL, payload_json JSONB NOT NULL, updated_at_utc TIMESTAMPTZ NOT NULL);
CREATE TABLE agent_performance_observations (observation_id TEXT PRIMARY KEY, target_id TEXT NOT NULL, capability_id TEXT NOT NULL, success BOOLEAN NOT NULL, payload_json JSONB NOT NULL, observed_at_utc TIMESTAMPTZ NOT NULL);
CREATE TABLE agent_routing_decisions (decision_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, selected_provider_id TEXT, payload_json JSONB NOT NULL, created_at_utc TIMESTAMPTZ NOT NULL);
CREATE TABLE agent_execution_receipts (receipt_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, succeeded BOOLEAN NOT NULL, payload_json JSONB NOT NULL, created_at_utc TIMESTAMPTZ NOT NULL);
CREATE TABLE agent_qualification_reports (report_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, subject_version TEXT NOT NULL, state TEXT NOT NULL, payload_json JSONB NOT NULL, evaluated_at_utc TIMESTAMPTZ NOT NULL);
CREATE INDEX idx_agent_perf_target_capability ON agent_performance_observations(target_id, capability_id);
CREATE INDEX idx_agent_route_task ON agent_routing_decisions(task_id, created_at_utc);
