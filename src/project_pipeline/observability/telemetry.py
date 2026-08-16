from __future__ import annotations

from dataclasses import asdict, dataclass

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from project_pipeline.configuration.models import TelemetryExporter, TelemetrySettings


@dataclass(frozen=True, slots=True)
class TelemetryBootstrapStatus:
    enabled: bool
    service_name: str
    provider: str
    exporter_state: str
    endpoint_configured: bool

    def as_dict(self) -> dict[str, bool | str]:
        return asdict(self)


def build_tracer_provider(settings: TelemetrySettings, environment: str) -> TracerProvider | None:
    if not settings.enabled:
        return None
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.namespace": settings.service_namespace,
            "deployment.environment.name": environment,
        }
    )
    return TracerProvider(resource=resource)


def telemetry_status(settings: TelemetrySettings) -> TelemetryBootstrapStatus:
    if not settings.enabled:
        return TelemetryBootstrapStatus(
            enabled=False,
            service_name=settings.service_name,
            provider="disabled",
            exporter_state="DISABLED",
            endpoint_configured=False,
        )
    exporter_state = (
        "CONFIGURED_NOT_ACTIVATED"
        if settings.exporter is TelemetryExporter.OTLP_HTTP
        else "LOCAL_ONLY"
    )
    return TelemetryBootstrapStatus(
        enabled=True,
        service_name=settings.service_name,
        provider="OpenTelemetry",
        exporter_state=exporter_state,
        endpoint_configured=settings.otlp_endpoint is not None,
    )
