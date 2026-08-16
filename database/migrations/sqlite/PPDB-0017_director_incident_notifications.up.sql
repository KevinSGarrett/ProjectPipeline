CREATE TABLE IF NOT EXISTS command_center_director_messages (
  message_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  role TEXT NOT NULL,
  scope TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_command_center_director_conversation
  ON command_center_director_messages(conversation_id, created_at_utc);

CREATE TABLE IF NOT EXISTS command_center_incident_cases (
  incident_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  state TEXT NOT NULL,
  severity INTEGER NOT NULL,
  updated_at_utc TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_command_center_incident_open
  ON command_center_incident_cases(project_id, state, severity);

CREATE TABLE IF NOT EXISTS command_center_notification_deliveries (
  delivery_id TEXT PRIMARY KEY,
  notification_id TEXT NOT NULL,
  inbox_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  adapter_id TEXT NOT NULL,
  state TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  created_at_utc TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_command_center_delivery_notification
  ON command_center_notification_deliveries(notification_id, channel, attempt_number);
