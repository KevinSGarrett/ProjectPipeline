CREATE TABLE IF NOT EXISTS command_center_events (
  event_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, sequence INTEGER NOT NULL,
  event_type TEXT NOT NULL, occurred_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_command_center_events_project_sequence ON command_center_events(project_id, sequence);
CREATE TABLE IF NOT EXISTS command_center_inbox (
  inbox_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, dedupe_key TEXT NOT NULL,
  level INTEGER NOT NULL, state TEXT NOT NULL, priority_score INTEGER NOT NULL,
  created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_command_center_inbox_open ON command_center_inbox(project_id,state,priority_score);
CREATE TABLE IF NOT EXISTS command_center_notifications (
  notification_id TEXT PRIMARY KEY, inbox_id TEXT NOT NULL, level INTEGER NOT NULL,
  suppressed INTEGER NOT NULL, decided_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS command_center_control_requests (
  request_id TEXT PRIMARY KEY, command_id TEXT NOT NULL, actor_id TEXT NOT NULL,
  status TEXT NOT NULL, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL
);
