-- PPDB-0019: enforce append-only audit history at the database boundary.
CREATE TRIGGER security_audit_events_no_update
BEFORE UPDATE ON security_audit_events
BEGIN
  SELECT RAISE(ABORT, 'security_audit_events is append-only');
END;

CREATE TRIGGER security_audit_events_no_delete
BEFORE DELETE ON security_audit_events
BEGIN
  SELECT RAISE(ABORT, 'security_audit_events is append-only');
END;
