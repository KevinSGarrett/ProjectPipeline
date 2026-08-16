-- BROKEN migration: references a table before it exists and cannot roll back safely
ALTER TABLE incident ADD COLUMN evidence_json TEXT;
DROP TABLE incident_history;
