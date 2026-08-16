# Logging and Telemetry

Structured logs include project, workflow, task, run, actor, correlation, and causation identities when available. Sensitive field names and Pydantic secret types are redacted before serialization. Bytes are summarized by length rather than emitted.

OpenTelemetry is the portable trace boundary. The local provider can be enabled without a remote exporter; OTLP export remains profile-gated and requires an endpoint. Telemetry failure must not become authoritative workflow failure.
