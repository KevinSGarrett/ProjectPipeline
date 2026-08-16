-- PPDB-0019: enforce append-only audit history at the database boundary.
CREATE OR REPLACE FUNCTION project_pipeline_reject_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'security_audit_events is append-only';
END;
$$;

CREATE TRIGGER security_audit_events_no_update
BEFORE UPDATE ON security_audit_events
FOR EACH ROW EXECUTE FUNCTION project_pipeline_reject_audit_mutation();

CREATE TRIGGER security_audit_events_no_delete
BEFORE DELETE ON security_audit_events
FOR EACH ROW EXECUTE FUNCTION project_pipeline_reject_audit_mutation();
