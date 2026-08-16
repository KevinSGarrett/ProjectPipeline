-- PPDB-0015 resilience, recovery, local runtime, and restore verification state
CREATE TABLE resilience_machines (machine_id TEXT PRIMARY KEY, healthy BOOLEAN NOT NULL, heartbeat_at_utc TIMESTAMPTZ NOT NULL, fencing_token BIGINT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE resilience_failover_decisions (decision_id TEXT PRIMARY KEY, eligible BOOLEAN NOT NULL, decided_at_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE resilience_operating_modes (decision_id TEXT PRIMARY KEY, mode TEXT NOT NULL, decided_at_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE resilience_incidents (incident_id TEXT PRIMARY KEY, failure_domain TEXT NOT NULL, created_at_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE resilience_recovery_objectives (objective_id TEXT PRIMARY KEY, domain TEXT NOT NULL UNIQUE, rpo_seconds INTEGER NOT NULL, rto_seconds INTEGER NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE resilience_backups (backup_id TEXT PRIMARY KEY, domain TEXT NOT NULL, completed BOOLEAN NOT NULL, created_at_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE resilience_restore_verifications (restore_id TEXT PRIMARY KEY, backup_id TEXT NOT NULL, state TEXT NOT NULL, verified_at_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL);
CREATE INDEX idx_resilience_machine_health ON resilience_machines(healthy, heartbeat_at_utc);
CREATE INDEX idx_resilience_backup_domain ON resilience_backups(domain, created_at_utc);
CREATE INDEX idx_resilience_restore_backup ON resilience_restore_verifications(backup_id, verified_at_utc);
