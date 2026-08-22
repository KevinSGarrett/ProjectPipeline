from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from typing import Any

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


def build_tracer_provider(settings: TelemetrySettings, environment: str) -> Any | None:
    if not settings.enabled:
        return None
    try:
        resource_module = importlib.import_module("opentelemetry.sdk.resources")
        trace_module = importlib.import_module("opentelemetry.sdk.trace")
    except ImportError:
        return None
    resource_type = resource_module.Resource
    tracer_provider_type = trace_module.TracerProvider
    resource = resource_type.create(
        {
            "service.name": settings.service_name,
            "service.namespace": settings.service_namespace,
            "deployment.environment.name": environment,
        }
    )
    return tracer_provider_type(resource=resource)


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
