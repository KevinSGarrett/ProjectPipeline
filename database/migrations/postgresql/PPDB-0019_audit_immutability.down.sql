DROP TRIGGER IF EXISTS security_audit_events_no_delete ON security_audit_events;
DROP TRIGGER IF EXISTS security_audit_events_no_update ON security_audit_events;
DROP FUNCTION IF EXISTS project_pipeline_reject_audit_mutation();
